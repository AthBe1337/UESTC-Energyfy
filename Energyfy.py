from utils.RoomInfo import RoomInfo

queries = [
    "XXXXXX",
    "XXXXXX",
    "XXXXXX",
    "XXXXXX",
    "XXXXXX",
    "XXXXXX",
    "XXXXXX",
]

room_info = RoomInfo("YOUR_STUDENT_ID", "YOUR_PASSWORD", queries)
results = room_info.get()

for result in results:
    print(f"房间 {result['roomName']} 余额为 {result['syje']}")