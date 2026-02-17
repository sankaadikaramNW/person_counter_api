from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import pytz
import asyncio

from sqlalchemy import create_engine, Column, Integer, String, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker


# ===== SYSTEM CONFIGURATION =====
OFFLINE_TIMEOUT = 8   # seconds → if no data received within 8s, mark sensor offline

# ================= DATABASE =================

DATABASE_URL = "postgresql://personuser:4zbHpRhdJtdZKmQCNv6AUouMGuwUg9Oq@dpg-d69nac3nv86c73f2hdcg-a.singapore-postgres.render.com/personcounter"


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ================= APP =================

app = FastAPI()

# Allow external devices (NodeMCU from any network)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SL_TZ = pytz.timezone("Asia/Colombo")

# ================= MODEL =================

class PersonCount(Base):
    __tablename__ = "person_counts"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String)
    batch = Column(Integer)
    total = Column(Integer)
    timestamp = Column(DateTime(timezone=True))
    status = Column(String)
    last_seen = Column(DateTime(timezone=True))

Base.metadata.create_all(bind=engine)

# ================= REQUEST MODEL =================

class PersonData(BaseModel):
    sensor_id: str
    batch: int
    total: int

# ================= RECEIVE DATA =================

@app.post("/api/person-count")
def receive_data(data: PersonData):
    db = SessionLocal()

    try:
        now_sl = datetime.now(SL_TZ)

        record = PersonCount(
            sensor_id=data.sensor_id,
            batch=data.batch,
            total=data.total,
            timestamp=now_sl,
            status="ONLINE",
            last_seen=now_sl
        )

        db.add(record)
        db.commit()

        return {"message": "stored"}

    finally:
        db.close()

# ================= SENSOR STATUS =================

@app.get("/api/sensor-status")
def get_sensor_status():
    db = SessionLocal()

    try:
        sensors = db.query(PersonCount.sensor_id).distinct().all()
        result = []

        for (sensor_id,) in sensors:
            latest = (
                db.query(PersonCount)
                .filter(PersonCount.sensor_id == sensor_id)
                .order_by(desc(PersonCount.timestamp))
                .first()
            )

            if latest:
                result.append({
                    "sensor_id": sensor_id,
                    "status": latest.status,
                    "last_seen": latest.last_seen.isoformat(),
                    "batch": latest.batch,
                    "total": latest.total
                })

        return result

    finally:
        db.close()

# ================= AUTO OFFLINE DETECTION =================

async def check_offline_sensors():
    while True:
        await asyncio.sleep(10)

        db = SessionLocal()
        try:
            now_sl = datetime.now(SL_TZ)
            timeout = now_sl - timedelta(seconds=OFFLINE_TIMEOUT)

            sensors = db.query(PersonCount.sensor_id).distinct().all()

            for (sensor_id,) in sensors:

                latest = (
                    db.query(PersonCount)
                    .filter(PersonCount.sensor_id == sensor_id)
                    .order_by(desc(PersonCount.timestamp))
                    .first()
                )

                # ✅ IMPORTANT SAFETY CHECK
                if latest and latest.last_seen is not None:

                    if latest.last_seen < timeout:
                        if latest.status != "OFFLINE":
                            latest.status = "OFFLINE"
                            print(f"{sensor_id} marked OFFLINE")

            db.commit()

        except Exception as e:
            print("Offline checker error:", e)

        finally:
            db.close()




@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_offline_sensors())
