import docker
import json

def listen_docker_events():
    client = docker.from_env()
    
    try:
        # Get the event stream
        event_stream = client.events(decode=True)
        
        print("Listening for Docker events... (Ctrl+C to stop)")
        for event in event_stream:
            print(json.dumps(event, indent=2))
            
    except KeyboardInterrupt:
        print("\nStopped listening to Docker events")
    finally:
        client.close()

if __name__ == "__main__":
    listen_docker_events()