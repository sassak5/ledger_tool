"""パーサパッケージ — レジストリへの登録"""

from src.core.parsers.bank import BankParser
from src.core.parsers.amazon import AmazonParser
from src.core.registry import registry

registry.register("bank_statement", BankParser)
registry.register("amazon_settlement_report", AmazonParser)
