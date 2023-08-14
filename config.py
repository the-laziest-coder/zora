RPCs = {
    'Ethereum': 'https://eth.llamarpc.com',
    'Zora': 'https://rpc.zora.energy',
    'Optimism': 'https://optimism.publicnode.com',
    'Base': 'https://mainnet.base.org',
}

###############################################################################################################

# Время ожидания между выполнением разных акков рандомное в указанном диапазоне
NEXT_ADDRESS_MIN_WAIT_TIME = 0.5  # В минутах
NEXT_ADDRESS_MAX_WAIT_TIME = 1  # В минутах

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
MAX_ETH_GAS_PRICE = 13.5

# Сколько секунд ждать до следующей проверки газ прайса
WAIT_GAS_TIME = 10
# Сколько всего секунд ждать лучшего газ прайса,
# если за это время газ прайс не понизится до нужного значения, будет ошибка
TOTAL_WAIT_GAS_TIME = 36000

###############################################################################################################

# Использовать Max base fee и Priority fee 0.005 для минта в Zora, экономия 0.3-0.5$
ZORA_LOW_GAS = True
# Использовать Max base fee и Priority fee 0.005 для минта в Base, экономия 0.3-0.5$
BASE_LOW_GAS = True

###############################################################################################################

# Модули, которые будут выполняться на каждом акке
# 'mint' - минт рандомной нфт из files/mints.txt, которой еще нет на акке
# 'admin' - минт рандомной нфт среди созданных, нет комиссии 0.000777
# 'create' - создание своей ERC721 нфт
# 'update' - обновить параметры рандомной созданной ERC721 коллекции
# 'bridge' - бридж из эфира в зору
MODULES = ['mint', 'mint', 'create', 'create', 'update', 'update', 'admin', 'admin']

# Выполнять модули в рандомном порядке для каждого акка
MODULES_RANDOM_ORDER = True

# В каких сетях минтить NFT. Все NFT из files/mints.txt в других сетях, будут игнорироваться
MINT_CHAINS = ['Zora']
# Минтить только custom NFT, пропуская все остальные из files/mints.txt
MINT_ONLY_CUSTOM = False
# Если у вас есть mint.fun Pass, то добавятся поинты за минты
MINT_WITH_MINT_FUN = True

# Сколько раз максимум можно минтить одну нфт. (Для кастомных проверяется MAX_NFT_PER_ADDRESS * cnt)
MAX_NFT_PER_ADDRESS = 10

# Сколько минтить собственных нфт, выбирается рандомное в указанном диапазоне
ADMIN_MINT_COUNT = (1, 3)

# При update используется рандомное действие из включенных ниже.
# Обновлять картинку NFT
UPDATE_IMAGE = True
# Обновлять описание
UPDATE_DESCRIPTION = True
# Обновлять настройки сейла: цена, лимит минта на один адрес
UPDATE_SALE_SETTINGS = True

# Какую цену указывать для нфт при обновлении настроек сейла и создании. Значение округляется до 6 знаков
MINT_PRICE = (0.000001, 0.0001)

# При True, если для минта или создания NFT в Зоре не хватает эфира, автоматически делать бридж
AUTO_BRIDGE = True
# Сколько бриджить эфира в Zora. Выбирается рандомное значение в диапазоне
BRIDGE_AMOUNT = (0.005, 0.0065)
# Сколько максимум ждать бриджа. Баланс проверяется каждые 20 секунд
BRIDGE_WAIT_TIME = 300
