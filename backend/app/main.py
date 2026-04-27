from fastapi import FastAPI
from starlette.requests import Request
from datetime import datetime
import socketio

from app.routers import buoy, data, alert, statistics, auth, commands
from app.services.websocket import sio
from app.config import get_settings
from app.database import engine, Base

settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="海洋浮标监测信息管理与分析平台",
    description="OBMAP API",
    version="1.0.0"
)

# Include routers
app.include_router(buoy.router)
app.include_router(data.router)
app.include_router(alert.router)
app.include_router(statistics.router)
app.include_router(auth.router)
app.include_router(commands.router)


# Create Socket.IO ASGI app
socket_app = socketio.ASGIApp(sio, app)


@app.get("/")
async def root():
    return {"message": "Ocean Buoy Monitoring API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}


@app.on_event("startup")
async def startup_event():
    print("=" * 60)
    print("Starting OBMAP Backend...")
    print("=" * 60)

    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        print("[Startup] Database tables verified")
    except Exception as e:
        print(f"[Startup] Database error: {e}")

    # Initialize MQTT service (EMQX)
    mqtt_service = None
    mqtt_max_retries = 5
    for attempt in range(mqtt_max_retries):
        try:
            from app.services.mqtt import init_mqtt_service
            mqtt_service = init_mqtt_service(
                broker_host=settings.mqtt_broker_host,
                broker_port=settings.mqtt_broker_port,
                username=settings.mqtt_username,
                password=settings.mqtt_password
            )
            if mqtt_service.connect():
                print(f"[Startup] MQTT service connected to EMQX at {settings.mqtt_broker_host}:{settings.mqtt_broker_port}")
                app.state.mqtt_service = mqtt_service
                break
            else:
                print(f"[Startup] MQTT connection attempt {attempt + 1}/{mqtt_max_retries} failed")
        except Exception as e:
            print(f"[Startup] MQTT init error (attempt {attempt + 1}): {e}")

        import time
        if attempt < mqtt_max_retries - 1:
            print(f"[Startup] Retrying MQTT connection in 5s...")
            time.sleep(5)

    if mqtt_service is None or not mqtt_service.is_connected():
        print("[Startup] WARNING: MQTT not connected, will operate in fallback mode (direct DB)")

    # Initialize data simulator
    if settings.simulator_enabled:
        import threading
        from app.simulator.simulator import DataSimulator
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            simulator = DataSimulator(mqtt_service=mqtt_service)
            simulator.initialize(db)
            app.state.simulator = simulator
            print(f"[Startup] Initialized {len(simulator.buoys)} simulated buoys")

            def run_data_generation():
                while True:
                    import time
                    time.sleep(10)
                    try:
                        db_gen = SessionLocal()
                        try:
                            data_list = simulator.generate_data(db_gen)
                            # Note: data is saved to DB via MQTT handler if connected
                            # Otherwise saved directly in generate_data()

                            alerts = simulator.check_alerts(db_gen, data_list)
                            for alert in alerts:
                                db_gen.add(alert)
                            if alerts:
                                db_gen.commit()
                                print(f"[Simulator] {len(alerts)} alerts triggered")
                        finally:
                            db_gen.close()
                    except Exception as e:
                        print(f"[Simulator] Data generation error: {e}")

            thread = threading.Thread(target=run_data_generation, daemon=True)
            thread.start()
            print("[Startup] Data simulation thread started")
        except Exception as e:
            print(f"[Startup] Simulator error: {e}")
        finally:
            db.close()

    print("=" * 60)
    print("OBMAP Backend Started Successfully")
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    print("[Shutdown] Stopping OBMAP Backend...")
    if hasattr(app.state, 'mqtt_service') and app.state.mqtt_service:
        app.state.mqtt_service.disconnect()
        print("[Shutdown] MQTT disconnected")
    print("[Shutdown] Done")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(socket_app, host="0.0.0.0", port=8000)
