"""Small synthetic evidence that is analyzed with the same public engine."""
from __future__ import annotations

from pathlib import Path

from .config import dump_config
from .models import AuditConfig, InputError
from .output import write_outputs

ORDERS = '''order_id,customer_id,amount
O-1001,C001,100.00
O-1002,C002,90.00
O-1003,C003,-30.00
O-1004,C004,90.00
'''
CUSTOMERS = '''customer_id,segment
C001,Retail
C001,Wholesale
C001,Partner
C002,Retail
C002,Partner
C003,Retail
C003,Wholesale
C005,Prospect
'''


def prepare_demo(directory: Path) -> AuditConfig:
    if directory.exists() and any(directory.iterdir()):
        raise InputError('Demo directory must be new or empty; existing files are never replaced.')
    directory.mkdir(parents=True, exist_ok=True)
    config = AuditConfig(
        left=directory / 'orders.csv', right=directory / 'customers.csv',
        left_keys=('customer_id',), right_keys=('customer_id',), amount_column='amount',
        relationship='many-to-one', join_type='left',
    )
    write_outputs([
        (config.left, ORDERS), (config.right, CUSTOMERS),
        (directory / 'audit.json', dump_config(config, directory / 'audit.json')),
    ], [], False)
    return config
