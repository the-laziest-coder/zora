RPCs = {
    'Ethereum': 'https://rpc.ankr.com/eth',
    'Zora': 'https://rpc.zora.energy',
    'Optimism': 'https://optimism.publicnode.com',
    'Base': 'https://mainnet.base.org',
    'Arbitrum': 'https://rpc.ankr.com/arbitrum',
}

###############################################################################################################

# Время ожидания между выполнением разных акков рандомное в указанном диапазоне
NEXT_ADDRESS_MIN_WAIT_TIME = 1  # В минутах
NEXT_ADDRESS_MAX_WAIT_TIME = 2  # В минутах

# Время ожидания между действиями одного аккаунта
NEXT_TX_MIN_WAIT_TIME = 8   # В секундах
NEXT_TX_MAX_WAIT_TIME = 15  # В секундах

# Максимальное кол-во попыток сделать запрос/транзакцию если они фейлятся
MAX_TRIES = 3

###############################################################################################################

# Токен и chat id бота в тг. Можно оставить пустым.
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = 0
# При True, скрипт только выдает ваш chat id для отправки сообщений в боте.
GET_TELEGRAM_CHAT_ID = False

###############################################################################################################

# Максимальный газ прайс в Gwei, при котором делать транзакции в Ethereum
MAX_ETH_GAS_PRICE = 15
# Максимальный газ прайс в Gwei в Ethereum, при котором делать транзакции в L2 сетях
MAX_ETH_GAS_PRICE_FOR_L2 = 40

# Сколько секунд ждать до следующей проверки газ прайса
WAIT_GAS_TIME = 60
# Сколько всего секунд ждать лучшего газ прайса,
# если за это время газ прайс не понизится до нужного значения, будет ошибка
TOTAL_WAIT_GAS_TIME = 360000

###############################################################################################################

# Использовать Max base fee и Priority fee 0.005 для минта в Zora, экономия 0.3-0.5$
ZORA_LOW_GAS = True
# Использовать Max base fee и Priority fee 0.005 для минта в Base, экономия 0.3-0.5$
BASE_LOW_GAS = True

###############################################################################################################

# Модули, которые будут выполняться на каждом акке
# 'mint' - минт рандомной нфт из files/mints.txt, которой еще нет на акке
# 'admin' - минт рандомной нфт среди созданных, нет комиссии 0.000777
# 'create' - создание своей нфт
# 'update' - обновить параметры рандомной созданной ERC721 коллекции
# 'bridge' - бридж из эфира в зору
# 'claim' - клейм ревардов в Base и Zora. В Zora 2 клейма отдельных
# Формат - <действие>: (<минимальное кол-во>, <максимальное кол-во>)
# Для каждого акка и действия выбирается рандомное кол-во транзакций в указанном диапазоне
MODULES = {
    'mint': (1, 1),
    'admin': (0, 0),
    'create': (0, 0),
    'update': (0, 0),
    'bridge': (0, 0),
    'claim': (1, 1),
}

# В каких сетях минтить NFT. Все NFT из files/mints.txt в других сетях, будут игнорироваться
MINT_CHAINS = ['Zora']
# Минтить только custom NFT, пропуская все остальные из files/mints.txt
MINT_ONLY_CUSTOM = False
# Если у вас есть mint.fun Pass, то добавятся поинты за минты
MINT_WITH_MINT_FUN = True
# С каким процентом минтить любую NFT из уже созданных коллекций среди всех акков
# Если значение > 0, то при страте скрипта сначала для всех аккаунтов будут запрашиваться созданные коллекции
# Это может занять некоторое время, если кошельков много
MINT_ALREADY_CREATED_PERCENT = 50

# Сколько раз максимум можно минтить одну нфт. (Для кастомных проверяется MAX_NFT_PER_ADDRESS * cnt)
MAX_NFT_PER_ADDRESS = 10

# Сейчас через интерфейс можно создавать только ERC1155 коллекции,
# но в коде остается возможность создавать ERC721 через контракт
# Все ERC1155 NFT создаются бесплатными, с рандомным значением auto-reserve.
# Используется также для авто-создание при admin и update
USE_NFT_1155 = True
# Если при исполнении действия admin или update нет созданной NFT на кошельке автоматически создавать коллекцию
AUTO_CREATE = True

# Процент от 0 до 100, с какой вероятностью создавать новую ERC1155 NFT в существующей коллекции,
# а не создавать новую коллекцию
CREATE_USING_EXISTED_COLLECTION_PROBABILITY = 50

# При update используется рандомное действие из включенных ниже.

# Настройки обновления ERC721 коллекций:
# Обновлять картинку NFT для ERC721
UPDATE_IMAGE_ERC721 = True
# Обновлять описание
UPDATE_DESCRIPTION_ERC721 = True
# Обновлять настройки сейла: цена, лимит минта на один адрес
UPDATE_SALE_SETTINGS_ERC721 = True
# Какую цену указывать для нфт при обновлении настроек сейла и создании ERC721 NFT. Значение округляется до 6 знаков
MINT_PRICE = (0.000001, 0.0001)

# Настройки обновления ERC1155 коллекций:
# Обновлять название/описание/картинку коллекции
UPDATE_COLLECTION_ERC1155 = True
# Обновлять название/описание/картинку NFT
UPDATE_NFT_ERC1155 = True

# При True, если для минта или создания NFT в Зоре не хватает эфира, автоматически делать бридж
AUTO_BRIDGE = True
# Сколько максимум авто-бриджей скрипт может сделать на один акк
AUTO_BRIDGE_MAX_CNT = 1
# Сколько бриджить эфира в Zora. Выбирается рандомное значение в диапазоне
BRIDGE_AMOUNT = (0.005, 0.0065)
# Сколько максимум ждать бриджа. Баланс проверяется каждые 20 секунд
BRIDGE_WAIT_TIME = 300

# Вместо оф бриджа делать рефуел из Arbitrum или Optimism в Zora через Zerius
REFUEL_WITH_ZERIUS = True
# При BRIDGE_WITH_ZERIUS = True, из какой сети делать рефуел,
# Доступные сети: 'Arbitrum', 'Optimism'
ZERIUS_SOURCE_CHAIN = 'Optimism'

# Если ревардов меньше, чем указанная сумма, то клема не будет.
MIN_REWARDS_TO_CLAIM = 0.001
# В каких сетях делать клейм ревардов. Доступны только Zora и Base
REWARDS_CHAINS = ['Zora', 'Base']

IMAP_SERVER = 'imap-mail.outlook.com'
EMAIL_FOLDERS = ['INBOX', 'JUNK']
# Если email уже привязан и верифнут, все равно менять на новый (если он новый) при запуске скрипта,
# иначе изменений не будет
UPDATE_EMAIL_IF_VERIFIED = False

# Сколько потоков использовать для чекера
CHECKER_THREADS = 10
