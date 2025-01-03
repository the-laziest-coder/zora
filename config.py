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
MAX_ETH_GAS_PRICE_FOR_L2 = 80

# Сколько секунд ждать до следующей проверки газ прайса
WAIT_GAS_TIME = 60
# Сколько всего секунд ждать лучшего газ прайса,
# если за это время газ прайс не понизится до нужного значения, будет ошибка
TOTAL_WAIT_GAS_TIME = 360000

###############################################################################################################

# Использовать Max base fee и Priority fee 0.005 для минта в Zora, экономия 0.3-0.5$
ZORA_LOW_GAS = False
# Использовать Max base fee и Priority fee 0.005 для минта в Base, экономия 0.3-0.5$
BASE_LOW_GAS = False

###############################################################################################################

OKX_API_KEY = ''
OKX_SECRET_KEY = ''
OKX_PASSPHRASE = ''
OKX_WITHDRAW_ETH_AMOUNT = (0.007, 0.01)

###############################################################################################################

# Модули, которые будут выполняться на каждом акке
# 'mint' - минт рандомной нфт из files/mints.txt, которой еще нет на акке
# 'sale' - продать нфт, только те, которые минтились за ✧111
# 'admin' - минт рандомной нфт среди созданных, нет комиссии 0.000777
# 'create' - создание своей нфт
# 'update' - обновить параметры рандомной созданной ERC721 коллекции
# 'bridge' - бридж из эфира в зору
# 'claim' - клейм ревардов в Base и Zora. В Zora 2 клейма отдельных
# 'personalize' - рандомное персонализирование профиля
# 'swap' - делать свап, каждое действия дублируется на обратный свап в ETH
# Формат - <действие>: (<минимальное кол-во>, <максимальное кол-во>)
# Для каждого акка и действия выбирается рандомное кол-во транзакций в указанном диапазоне
MODULES = {
    'mint': (1, 1),
    'sale': (0, 0),
    'admin': (0, 0),
    'create': (0, 0),
    'update': (0, 0),
    'bridge': (0, 0),
    'claim': (0, 0),
    'personalize': (0, 0),
    'swap': (0, 0),
}

MINT_CNT = 1

# Достать все созданные нфт (ссылки на них) на всех кошельках
# Остальные действия не делаются
EXTRACT_CREATED_NFTS = False

# Выполнять в рандомном порядке все действия всех кошельков, а не все действия одного кошелька подряд
# Между всеми действиями будет использоваться задержка NEXT_ADDRESS_MIN_WAIT_TIME-NEXT_ADDRESS_MAX_WAIT_TIME
FULL_SHUFFLE = False

# Распределять кол-во минтов по нфт, а не по кошелькам.
# Для этого в files/mints.txt все нфт должны быть указаны в формате:
# link|min_cnt-max_cnt или link|cnt
# Требования: MINT_ALREADY_CREATED_PERCENT = 0
MINT_BY_NFTS = False

# Логиниться при каждом действии, можно отключить, но AI генерация изображений работать не будет
DO_LOGIN = False

# Список NFT для продажи, только который минтились за ✧111
# Формат: (contract address, token id)
SALE_NFTS = [
    ('0x86aF55FC811FEF6f9729D32aDcf2c253CA5A16C1', 2),  # Limitless Zorb
]
# Сколько NFT продавать в процентах от баланса
SALE_AMOUNT_PERCENT = 10
# При сколько иксах от минта продавать, если меньше, то не будет продавать
SALE_MINIMUM_PROFIT_X = 4

# Рандомит только четное кол-во свапов, чтобы в конце остался ETH. Последний свап на акке всегда будет только в ETH
EVEN_NUMBER_OF_SWAPS = True
SWAP_TOKEN_ADDRESSES = [
    '0xa6B280B42CB0b7c4a4F789eC6cCC3a7609A1Bc39',  # ENJOY
    '0x078540eECC8b6d89949c9C7d5e8E91eAb64f6696',  # IMAGINE
    '0xCccCCccc7021b32EBb4e8C08314bD62F7c653EC4',  # USDzC
]
# Делать свапы только в ETH
SWAP_ONLY_TO_ETH = False
# Минимальный баланс токена, из которого свапать
SWAP_MIN_BALANCE = {
    'ETH': 0.002,
    '0xa6B280B42CB0b7c4a4F789eC6cCC3a7609A1Bc39': 10000,  # ENJOY
    '0x078540eECC8b6d89949c9C7d5e8E91eAb64f6696': 1000,   # IMAGINE
    '0xCccCCccc7021b32EBb4e8C08314bD62F7c653EC4': 5,      # USDzC
}
SWAP_ETH_PERCENT = (30, 50)
SWAP_NON_ETH_PERCENT = (99, 100)

# При минте нфт за ERC-20 токены, софт свапает на ровно то количество токенов, которое нужно для 1 минта
# Можно добавить множитель для свапа, чтобы не свапать каждый раз
# Множитель будет рандомится в пределах от -10% до +10% от указанного
SWAP_MULTIPLIER_FOR_ERC20_MINT = 1.5

# С какой вероятностью покупать минты (рассчитывается перед каждым минтом), если их нет
# Уже недоступно через UI
BUY_PREPAID_MINTS_PROBABILITY = 0
# Сколько минтов покупать
BUY_PREPAID_MINTS_CNT = (1, 3)

# Добавлять рандомный комментарий к минту
MINT_WITH_COMMENT = True
# Вероятность оставить коммент в процентах
COMMENT_PROBABILITY = 15
# Максимальное кол-во слов в комменте, Выбирается рандомное
COMMENT_MAX_NUMBER_OF_WORDS = 1
COMMENT_WORDS = ['nice', 'lfg', 'enjoy', 'imagine', 'gm', 'minted', '!!!', 'based', 'like']
# Минтить только custom NFT, пропуская все остальные из files/mints.txt
MINT_ONLY_CUSTOM = False
# С каким процентом минтить любую NFT из уже созданных коллекций среди всех акков
# Если значение > 0, то при страте скрипта сначала для всех аккаунтов будут запрашиваться созданные коллекции
# Это может занять некоторое время, если кошельков много
MINT_ALREADY_CREATED_PERCENT = 0

# Сколько раз максимум можно минтить одну нфт. (Для кастомных проверяется MAX_NFT_PER_ADDRESS * cnt)
MAX_NFT_PER_ADDRESS = 20

# Если при исполнении действия admin или update нет созданной NFT на кошельке автоматически создавать коллекцию
AUTO_CREATE = True

# Процент от 0 до 100, с какой вероятностью создавать новую ERC1155 NFT в существующей коллекции,
# а не создавать новую коллекцию
CREATE_USING_EXISTED_COLLECTION_PROBABILITY = 50

# В какой сети создавать коллекцию, поддерживается только Zora и Base. Выбирается рандомная сеть из списка
CREATE_CHAIN = ['Zora', 'Base']

# Выбирает рандомное. Все доступные варианты приведены ниже
# Работает только для ERC20 коллекций
CREATE_MINT_DURATION = [
    # '1 hour', '4 hours', '24 hours',
    '3 days', '1 week', '1 month',
    '3 months', '6 months',
]
# С какой вероятностью создавать NFT с оплатой в другим токенах. Только в сети Zora
CREATE_FOR_ERC20_TOKENS_PROBABILITY = 0
# Какие токены использовать, их диапазон рандомной цены и до скольки занков после запятой округлять цену
CREATE_FOR_ERC20_TOKENS_PRICES = {
    '0xa6B280B42CB0b7c4a4F789eC6cCC3a7609A1Bc39': (100, 1000, 0),  # ENJOY
    '0x078540eECC8b6d89949c9C7d5e8E91eAb64f6696': (10, 100, 0),  # IMAGINE
    # '0xCccCCccc7021b32EBb4e8C08314bD62F7c653EC4': (0.01, 0.2, 2),  # USDzC
}
# Шанс на использование AI генерации для всех картинок
USE_AI_IMAGE_PROBABILITY = 100
# Реварды будут сплитится 80/10/10 (посмотрите как это работает на сайте)
USE_SPLIT_FOR_AI_IMAGE_PROBABILITY = 100
# Оставлять описание созданной коллекции/нфт пустым, иначе генерирует рандомное из слов в english_words.txt
EMPTY_DESCRIPTION = True

# Настройки обновления ERC1155 коллекций:
# Обновлять название/описание/картинку коллекции
UPDATE_COLLECTION_ERC1155 = True
# Обновлять название/описание/картинку NFT
UPDATE_NFT_ERC1155 = True

# Вместо оф бриджа делать инстант бридж из Arbitrum, Optimism или Base
USE_INSTANT_BRIDGE = True
# При REFUEL_WITH_INSTANT_BRIDGE = True, из какой сети делать бридж,
# Доступные сети: 'Arbitrum', 'Optimism', 'Base' или 'Any' - бридж из сети с максимальным балансом
BRIDGE_SOURCE_CHAIN = 'Any'

# При True, если для минта или создания NFT в Зоре не хватает эфира, автоматически делать бридж
AUTO_BRIDGE = True
# Сколько максимум авто-бриджей скрипт может сделать на один акк
AUTO_BRIDGE_MAX_CNT = 1
# Процент сколько эфира бриджить, если -1, то берется BRIDGE_AMOUNT
# Пример: (70, 80)
BRIDGE_PERCENT = -1
# Минимальный баланс, который должен быть при режиме бриджа в процентах
BRIDGE_PERCENT_MIN_BALANCE = 0.01
# Сколько бриджить эфира в Zora. Выбирается рандомное значение в диапазоне
BRIDGE_AMOUNT = (0.007, 0.009)
# Сколько максимум ждать бриджа. Баланс проверяется каждые 20 секунд
BRIDGE_WAIT_TIME = 300

# Если ревардов меньше, чем указанная сумма, то клема не будет.
# Указывается для каждого токена отдельно
MIN_REWARDS_TO_CLAIM = {
    'ETH': 0.0004,
    '0xa6B280B42CB0b7c4a4F789eC6cCC3a7609A1Bc39': 10000,  # ENJOY
    '0x078540eECC8b6d89949c9C7d5e8E91eAb64f6696': 500,    # IMAGINE
    # '0xCccCCccc7021b32EBb4e8C08314bD62F7c653EC4': 1,    # USDzC
}
# В каких сетях делать клейм ревардов. Доступны только Zora и Base
REWARDS_CHAINS = ['Zora', 'Base']

IMAP_SERVER = 'imap-mail.outlook.com'
EMAIL_FOLDERS = ['INBOX', 'JUNK']
# Если email уже привязан и верифнут, все равно менять на новый (если он новый) при запуске скрипта,
# иначе изменений не будет
UPDATE_EMAIL_IF_VERIFIED = False

# Сколько потоков использовать для чекера
CHECKER_THREADS = 10


REF = ''
