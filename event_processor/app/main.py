from app.database import Base, engine
from app.models import Event
from app.consumer import consume_events


Base.metadata.create_all(bind=engine)

print("Event Processor database ready.")

consume_events()