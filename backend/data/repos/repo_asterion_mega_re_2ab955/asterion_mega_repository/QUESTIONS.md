# Asterion stress-test questions

1. List all 24 services and count their source files.
2. Show the complete call graph of services.payments.service.service_operation_6.
3. Find all inbound callers of services.identity.validators.validators_operation_0.
4. Identify strongly connected components in the service dependency graph.
5. Find the shortest directed call path from gateway to audit and show each hop.
6. Which services depend transitively on payments? Distinguish imports from calls.
7. If services.inventory.repository changes, which services and tests might be affected?
8. Rank the top 20 functions by inbound CALLS degree.
9. Find classes inheriting from BaseProcessor across all services.
10. Find cross-service imports originating in checkout.
11. Which source files have the highest coupling by distinct imported modules?
12. List test files that reference each service and explain the relationship.
13. Find functions with more than three outgoing call relationships.
14. Show the smallest service dependency cycle containing payments.
15. Explain whether the graph proves a runtime outage in payments would impact gateway.
16. What is the difference between directly imported and transitively dependent modules in this fixture?
17. Which modules are isolated, if any?
18. Find all paths of length at most four from orders to notifications.
19. Explain how incremental indexing should update the graph after editing pricing/service.py.
20. Which dependencies are ambiguous without dynamic execution?
