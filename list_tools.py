#!/usr/bin/env python3
import os
os.environ['BIRRE_CONTEXT'] = 'risk_manager'

from birre import create_birre_server
from birre.config.settings import resolve_birre_settings
from birre.infrastructure.logging import get_logger

settings = resolve_birre_settings()
logger = get_logger('test')
server = create_birre_server(settings, logger=logger)

tools = server._list_tools()
print(f"\nTotal tools: {len(tools)}\n")

# Look for tree-related tools
tree_tools = [t for t in tools if 'tree' in t.name.lower() or 'Tree' in t.name]
print(f"Tools with 'tree': {len(tree_tools)}")
for tool in tree_tools:
    print(f"  - {tool.name}")

# Look for company-related tools
company_tools = [t for t in tools if t.name.startswith('get') and 'ompan' in t.name.lower()]
print(f"\nTools starting with 'get' and containing 'ompan': {len(company_tools)}")
for tool in company_tools:
    print(f"  - {tool.name}")
