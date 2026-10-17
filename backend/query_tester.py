from app.graph.client import falkor_client

# Cypher for "Which functions are defined in this file?"
q1 = """
MATCH (f:FILE {name: 'utils.py'})-[:DEFINES]->(sym:FUNCTION)
RETURN sym.name as function_name
"""

# Cypher for "Which modules import this module?"
q2 = """
MATCH (f:FILE)-[:IMPORTS]->(m:MODULE {name: 'utils'})
RETURN f.name as importer_file
"""

print("Query 1:", q1)
print("Query 2:", q2)
