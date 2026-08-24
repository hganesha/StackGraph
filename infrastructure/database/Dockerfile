FROM pgvector/pgvector:pg16 AS pgvector

# Local upgrades may reuse a volume initialized by the former AGE image. Keep the
# legacy library available during that transition while adding pgvector; application
# readiness and all new graph work depend only on pgvector + Neo4j.
FROM apache/age:release_PG16_1.6.0

COPY --from=pgvector /usr/lib/postgresql/16/lib/vector.so /usr/lib/postgresql/16/lib/vector.so
COPY --from=pgvector /usr/share/postgresql/16/extension/vector.control /usr/share/postgresql/16/extension/vector.control
COPY --from=pgvector /usr/share/postgresql/16/extension/vector--*.sql /usr/share/postgresql/16/extension/
