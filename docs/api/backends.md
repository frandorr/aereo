# Executors

Executors turn a sequence of `ExtractionTask` objects into a single validated
`GeoDataFrame[ArtifactSchema]`. AEREO provides `LocalExecutor` for local
execution and `LambdaExecutor` for serverless AWS Lambda execution.

::: aereo.executors
