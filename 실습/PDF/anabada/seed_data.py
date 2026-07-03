"""
테스트용 예시 데이터를 데이터베이스에 추가하는 스크립트

사용법:
    python seed_data.py
"""

from app import app, db
from models import Item, User

SAMPLE_USERS = [
    {"username": "kimminsoo", "password": "test1234"},
    {"username": "leejieun", "password": "test1234"},
]

SAMPLE_ITEMS = [
    {
        "title": "무선 이어폰",
        "description": "사용감 적은 블루투스 이어폰입니다. 충전 케이스 포함.",
        "price": 15000,
        "status": "거래가능",
        "author_username": "kimminsoo",
    },
    {
        "title": "소설 책 5권 세트",
        "description": "읽지 않은 소설 책 5권을 무료로 나눔합니다.",
        "price": 0,
        "status": "거래가능",
        "author_username": "leejieun",
    },
    {
        "title": "원목 책상",
        "description": "이사로 인해 책상을 나눔합니다. 직접 가져가셔야 합니다.",
        "price": 0,
        "status": "거래가능",
        "author_username": "kimminsoo",
    },
    {
        "title": "겨울 패딩 점퍼",
        "description": "M사이즈 패딩 점퍼, 1년 착용. 상태 양호합니다.",
        "price": 30000,
        "status": "거래가능",
        "author_username": "leejieun",
    },
    {
        "title": "주방 세제 세트",
        "description": "미개봉 주방 세제 3개 세트입니다.",
        "price": 5000,
        "status": "거래완료",
        "author_username": "kimminsoo",
    },
    {
        "title": "유아용 장난감",
        "description": "아이가 자랐어서 필요 없어진 장난감입니다. 깨끗하게 사용했습니다.",
        "price": 0,
        "status": "거래가능",
        "author_username": "leejieun",
    },
]


def seed():
    with app.app_context():
        db.create_all()

        existing = Item.query.count()
        if existing > 0:
            print(f"이미 {existing}개의 물품이 등록되어 있습니다.")
            answer = input("추가로 예시 데이터를 넣으시겠습니까? (y/n): ")
            if answer.lower() != "y":
                print("취소되었습니다.")
                return

        users = {}
        for data in SAMPLE_USERS:
            user = User.query.filter_by(username=data["username"]).first()
            if not user:
                user = User(username=data["username"])
                user.set_password(data["password"])
                db.session.add(user)
            users[data["username"]] = user

        db.session.commit()

        for data in SAMPLE_ITEMS:
            author = users[data["author_username"]]
            item = Item(
                title=data["title"],
                description=data["description"],
                price=data["price"],
                status=data["status"],
                author_id=author.id,
            )
            db.session.add(item)

        db.session.commit()
        print(f"사용자 {len(SAMPLE_USERS)}명, 물품 {len(SAMPLE_ITEMS)}개가 추가되었습니다.")
        print("테스트 계정: kimminsoo / test1234, leejieun / test1234")


if __name__ == "__main__":
    seed()
