import requests
import time
import uuid
import random

# Конфигурация
BASE_URL = "http://127.0.0.1:8000"  # Замените на IP сервера, если нужно
NUM_OFFLINE_USERS = 200  # Те, кто "пропадет" в центре
NUM_ONLINE_USERS = 100  # Те, кто будет "пинговать" по краям

# Координаты центра и точек на краях (МКАД)
MOSCOW_CENTER = (55.7558, 37.6173)
MOSCOW_EDGES = [
    (55.9098, 37.5876), # Север (Алтуфьево)
    (55.6328, 37.6014), # Юг (Чертаново)
    (55.7180, 37.3912), # Запад (Кунцево)
    (55.7286, 37.8431), # Восток (Выхино)
    (55.8288, 37.3305), # Северо-запад (Митино)
]

def generate_nearby(base_coord, spread=0.02):
    """Генерирует случайную координату в радиусе spread от базовой"""
    lat, lon = base_coord
    return (
        lat + random.uniform(-spread, spread),
        lon + random.uniform(-spread, spread)
    )

def send_ping(user_id, lat, lon):
    try:
        requests.post(f"{BASE_URL}/ping", params={"uuid": user_id, "lat": lat, "lon": lon}, timeout=5)
    except Exception as e:
        print(f"Ошибка пинга: {e}")

# --- ПОДГОТОВКА ДАННЫХ ---
print(f"Генерация {NUM_OFFLINE_USERS} оффлайн-пользователей в центре...")
offline_users = []
for _ in range(NUM_OFFLINE_USERS):
    u_id = str(uuid.uuid4())
    pos = generate_nearby(MOSCOW_CENTER, spread=0.015) # Центр плотнее
    offline_users.append({'id': u_id, 'pos': pos})

print(f"Генерация {NUM_ONLINE_USERS} онлайн-пользователей по краям...")
online_users = []
for _ in range(NUM_ONLINE_USERS):
    u_id = str(uuid.uuid4())
    edge_base = random.choice(MOSCOW_EDGES)
    pos = generate_nearby(edge_base, spread=0.01)
    online_users.append({'id': u_id, 'pos': pos})

# --- ЗАПУСК ТЕСТА ---

print("\n[ШАГ 1] Все пользователи делают первый пинг (регистрация)...")
for user in offline_users + online_users:
    send_ping(user['id'], user['pos'][0], user['pos'][1])

print("Все пользователи сейчас ONLINE. На карте должно быть пусто (обрывов нет).")
print("Ждем 10 секунд...")
time.sleep(10)

print(f"\n[ШАГ 2] Оффлайн-пользователи (центр) замолчали.")
print(f"Онлайн-пользователи (края) продолжают слать пинги...")

# Цикл симуляции
try:
    #iteration = 0
    #while True:
    for iteration in range(1000000):
        #iteration += 1
        print(f"Итерация {iteration}. Пингуем от онлайн-пользователей...")
        
        for user in online_users:
            # Слегка меняем координаты, имитируя движение или погрешность GPS
            current_pos = generate_nearby(user['pos'], spread=0.001)
            send_ping(user['id'], current_pos[0], current_pos[1])
        
        print("Ожидание 15 секунд...")
        time.sleep(15)
        
        if iteration == 3:
            print("\n!!! ПРОШЛО ДОСТАТОЧНО ВРЕМЕНИ !!!")
            print("Если OUTAGE_THRESHOLD_MINUTES в main.py стоит 0.5 (30 сек),")
            print("то сейчас в центре Москвы должны появиться красные кластеры.")
            print("Пользователи по краям Москвы НЕ ДОЛЖНЫ отображаться.")

    for user in offline_users:
        send_ping(user['id'], user['pos'][0], user['pos'][1])

except KeyboardInterrupt:
    print("\nТест остановлен.")
