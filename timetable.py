# timetable.py
# Simple school timetable data (edit this file to change it)

# Each day is a list of "periods".
# Each period is a dict:
#   {"time": "09:00-10:00", "title": "Maths", "room": "B12", "note": "Bring calculator"}

TIMETABLE = {
    "MON": [
        {"time": "09:00-13:00", "title": "group project", "room": "2Q13A", "note": ""},
    ],
    "TUE": [
        {"time": "10:00-11:00", "title": "internet of things lecture", "room": "2B025", "note": ""},
    ],
    "WED": [
        {"time": "09:00-11:00", "title": "internet of things practical", "room": "2Q13A", "note": ""},
    ],
    "THU": [
        {"time": "13:30-15:00", "title": "advanced algorithms practical", "room": "3Q085", "note": ""},
        {"time": "15:00-16:30", "title": "advanced algorithms lecture", "room": "2D067", "note": ""},
    ],
    "FRI": [
        {"time": "10:00-13:00", "title": "digital design", "room": "0T135", "note": ""},
    ],
}
