import asyncio
from aiodocker import Docker

async def monitor_events():
    async with Docker() as docker:
        subscriber = docker.events.subscribe()
        print("Listening for Docker events... (Ctrl+C to stop)")
        
        try:
            while True:
                event = await subscriber.get()
                if event is None:
                    break
                print("Event received:", event)
        except asyncio.CancelledError:
            print("\nStopped listening to events")

async def main():
    task = asyncio.create_task(monitor_events())
    try:
        await task
    except KeyboardInterrupt:
        task.cancel()
        await task

if __name__ == "__main__":
    asyncio.run(main())