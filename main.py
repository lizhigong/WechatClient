from enum import Enum
from wechat import WeChat

class Mode(Enum):
    NORMAL = 0,
    DEBUG = 1,
    BOT = 2


def main():
    client = WeChat()
    client.run()

if __name__ == '__main__':
    main()
