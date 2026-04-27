import socketio
from datetime import datetime

# Create Socket.IO server
# Note: Real-time data is now handled via MQTT
# This Socket.IO server is kept minimal for backward compatibility
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=['http://localhost:3000', 'http://localhost:8000'],
    ping_timeout=20,
    ping_interval=5
)


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")


@sio.event
async def subscribe(sid, data):
    """Handle client subscription to buoy data"""
    buoy_ids = data.get('buoy_ids', ['all'])

    if buoy_ids == ['all'] or buoy_ids == 'all':
        await sio.enter_room(sid, 'all_buoys')
    else:
        for buoy_id in buoy_ids:
            await sio.enter_room(sid, f'buoy_{buoy_id}')

    await sio.emit('subscribed', {
        'type': 'subscribed',
        'buoy_ids': buoy_ids,
        'timestamp': datetime.utcnow().isoformat()
    }, room=sid)


@sio.event
async def unsubscribe(sid, data):
    """Handle client unsubscription"""
    buoy_ids = data.get('buoy_ids', [])

    if 'all' in buoy_ids or buoy_ids == 'all':
        await sio.leave_room(sid, 'all_buoys')
    else:
        for buoy_id in buoy_ids:
            await sio.leave_room(sid, f'buoy_{buoy_id}')
