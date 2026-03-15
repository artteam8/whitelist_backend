import asyncio
from datetime import datetime, timedelta
from typing import List
import os

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import Column, String, Float, DateTime, Boolean, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import h3
import uvicorn

# --- КОНФИГУРАЦИЯ ---
DATABASE_URL = "sqlite:///./connection_tracker.db"
OUTAGE_THRESHOLD_MINUTES = 1  # Через сколько минут считать, что связь пропала
H3_RESOLUTION = 9  # Размер гексагона (~170 метров)

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- МОДЕЛИ БД ---
class User(Base):
    __tablename__ = "users"
    uuid = Column(String, primary_key=True, index=True)
    last_lat = Column(Float)
    last_lon = Column(Float)
    last_ping = Column(DateTime, default=datetime.utcnow)
    is_online = Column(Boolean, default=True)

class OutageZone(Base):
    __tablename__ = "outages"
    id = Column(String, primary_key=True)  # H3 Index
    last_seen = Column(DateTime, default=datetime.utcnow)
    intensity = Column(Integer, default=1)

# Создание таблиц при запуске
Base.metadata.create_all(bind=engine)

# --- ПРИЛОЖЕНИЕ ---
app = FastAPI()

# Разрешаем запросы из браузера (для index.html)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- ЛОГИКА КЛАСТЕРИЗАЦИИ ---
def create_h3_feature(h3_idx):
    try:
        boundary = h3.cell_to_boundary(h3_idx)
    except:
        boundary = h3.h3_to_geo_boundary(h3_idx)
    coords = [[float(p[1]), float(p[0])] for p in boundary]
    coords.append(coords[0])
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {"id": h3_idx}
    }

@app.get("/map")
async def get_map_data(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    limit_offline = now - timedelta(seconds=15)
    limit_dead = now - timedelta(hours=24)
    
    online_users = db.query(User).filter(User.last_ping >= limit_offline).all()
    online_hexes = set(h3.latlng_to_cell(u.last_lat, u.last_lon, 9) for u in online_users)
    
    offline_users = db.query(User).filter(
        User.last_ping < limit_offline,
        User.last_ping >= limit_dead
    ).all()
    offline_hexes = set(h3.latlng_to_cell(u.last_lat, u.last_lon, 9) for u in offline_users)

    #final_outage_hexes = list(offline_hexes - online_hexes)
    final_hexes = list(offline_hexes - online_hexes)
    
    #print(final_outage_hexes)
    print(final_hexes)

    #if not final_outage_hexes:
    if not final_hexes:
        return {"type": "FeatureCollection", "features": []}

    features = []
    for h_idx in final_hexes:
        try:
            boundary = h3.cell_to_boundary(h_idx)
        except:
            boundary = h3.h3_to_geo_boundary(h_idx)
            
        coords = [[float(p[1]), float(p[0])] for p in boundary]
        coords.append(coords[0])
        
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"id": h_idx}
        })
    
    return {"type": "FeatureCollection", "features": features}

    """
    # Пытаемся найти функцию объединения в разных версиях библиотеки
    try:
        if hasattr(h3, 'cells_to_polygons'):
            # Актуальный стандарт v4.x
            merged_polygons = h3.cells_to_polygons(final_outage_hexes)
        elif hasattr(h3, 'h3_set_to_multi_polygon'):
            # Старый стандарт v3.x
            merged_polygons = h3.h3_set_to_multi_polygon(final_outage_hexes, geo_json=False)
        else:
            # Если объединение не поддерживается, возвращаем одиночные гексагоны
            return create_individual_hexes_geojson(final_outage_hexes)
    except Exception as e:
        print(f"Ошибка объединения: {e}")
        return create_individual_hexes_geojson(final_outage_hexes)

    features = []
    for poly in merged_polygons:
        geojson_rings = []
        for ring in poly:
            # Конвертируем (lat, lng) -> [lng, lat]
            # ВНИМАНИЕ: в v4 h3.cells_to_polygons возвращает координаты в разном порядке 
            # в зависимости от системы. Проверим тип данных.
            ring_coords = [[float(c[1]), float(c[0])] for c in ring]
            if ring_coords[0] != ring_coords[-1]:
                ring_coords.append(ring_coords[0])
            geojson_rings.append(ring_coords)
            
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": geojson_rings},
            "properties": {"status": "offline"}
        })
    
    return {"type": "FeatureCollection", "features": features}
    """

def create_individual_hexes_geojson(hex_list):
    """Запасной метод: если объединение не работает, рисуем гексагоны по отдельности"""
    features = []
    for h_idx in hex_list:
        try:
            boundary = h3.cell_to_boundary(h_idx)
        except:
            boundary = h3.h3_to_geo_boundary(h_idx)
        coords = [[float(p[1]), float(p[0])] for p in boundary]
        coords.append(coords[0])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"status": "offline"}
        })
    return {"type": "FeatureCollection", "features": features}

# --- API ЭНДПОИНТЫ ---
@app.post("/ping")
async def ping(uuid: str, lat: float, lon: float, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uuid == uuid).first()
    now = datetime.utcnow()
    if not user:
        user = User(uuid=uuid, last_lat=lat, last_lon=lon, last_ping=now, is_online=True)
        db.add(user)
    else:
        user.last_lat, user.last_lon = lat, lon
        user.last_ping, user.is_online = now, True
    db.commit()
    return {"status": "ok"}



@app.get("/")
async def get_index():
    # Проверяем, существует ли файл, чтобы не было ошибки 500
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"error": "index.html not found on server"}


# --- BACKGROUND TASK ---
async def check_dead_connections():
    while True:
        await asyncio.sleep(30)
        db = SessionLocal()
        threshold = datetime.utcnow() - timedelta(minutes=5)
        db.query(User).filter(User.last_ping < threshold, User.is_online == True).update({"is_online": False})
        db.commit()
        db.close()

@app.on_event("startup")
async def startup_event():
    # Запуск фонового процесса
    asyncio.create_task(check_dead_connections())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)
