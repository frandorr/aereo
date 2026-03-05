from aer.plugin import plugin_registry
from aer.search import SearchQuery

print("--- AER CAPABILITY GRAPH ---")
plugin_registry.show_capabilities(SearchQuery)
print("----------------------------")
