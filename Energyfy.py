from utils.RoomInfo import RoomInfo

queries = [
    "121604",
    "121605",
    "121606",
    "121607",
    "121608",
    "121609",
    "121610",
]

room_info = RoomInfo("2022080912016", "wuyuyueWYY521", queries)
results = room_info.get()

for result in results:
    result = result[1]
    print(f"房间 {result['roomName']} 余额为 {result['syje']}")