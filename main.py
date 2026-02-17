from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
import pytz
import asyncio

from sqlalchemy import create_engine, Column, Integer, String, DateTime, desc
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ================= SYSTEM CONFIG =================

OFFLINE_TIMEOUT = 8  # seconds
SL_TZ = pytz.timezone("Asia/Colombo")

DATABASE_URL = "postgresql://personuser:4zbHpRhdJtdZKmQCNv6AUouMGuwUg9Oq@dpg-d69nac3nv86c73f2hdcg-a.singapore-postgres.render.com/personcounter"

# ================= DATABASE =================

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"sslmode": "require"}
)

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ================= MODELS =================

class PersonCount(Base):
    __tablename__ = "person_counts"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String, index=True)
    batch = Column(Integer)
    total = Column(Integer)
    timestamp = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True))
    status = Column(String)


Base.metadata.create_all(bind=engine)

# ================= APP =================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "Person Counter API is running"}


# ================= REQUEST MODEL =================

class PersonData(BaseModel):
    sensor_id: str
    batch: int
    total: int


# ================= RECEIVE PERSON COUNT =================

@app.post("/api/person-count")
def person_count(data: PersonData, db: Session = Depends(get_db)):

    now_sl = datetime.now(SL_TZ)

    new_record = PersonCount(
        sensor_id=data.sensor_id,
        batch=data.batch,
        total=data.total,
        timestamp=now_sl,
        last_seen=now_sl,
        status="ONLINE"
    )

    db.add(new_record)
    db.commit()

    return {"message": "Count stored successfully"}


# ================= SENSOR STATUS =================

@app.get("/api/sensor-status")
def get_sensor_status(db: Session = Depends(get_db)):

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
                "timestamp": latest.timestamp.isoformat(),
                "batch": latest.batch,
                "total": latest.total
            })

    return result


# ================= AUTO OFFLINE DETECTION =================

async def check_offline_sensors():
    while True:
        await asyncio.sleep(5)

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

                if latest and latest.last_seen:

                    if latest.last_seen < timeout and latest.status != "OFFLINE":
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
