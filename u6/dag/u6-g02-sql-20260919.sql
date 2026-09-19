-- ============================================================================
-- Grupo 2 - Gabriel Ernesto Escobar A00399291, David Artunduaga Penagos A00396342, Luis Manuel Rojas A00399289
-- Curso: Computación en la Nube para IA — Profesora: Diana Jaimes
-- Unidad 6 — Trabajo final: monitoreo del pipeline de retencion en produccion
-- ============================================================================

-- DDL para las tablas del pipeline U6 (Grupo 2).
-- Alineado con el patron de la guia de clase: 1 tabla `resultados`
-- (predicciones OK) + 1 tabla `cuarentena` (rechazos 422).
--
-- Nomenclatura por Pautas GCP (guion bajo para BQ):
--   dataset: u6_g02_data_20260919
--   tablas: resultados, cuarentena
--
-- Ubicacion: us-central1
-- Ejecutar con:
--   bq query --use_legacy_sql=false --location=us-central1 < u6-g02-sql-20260919.sql

CREATE SCHEMA IF NOT EXISTS `u6_g02_data_20260919`
  OPTIONS(location = "us-central1",
          description = "Trabajo final U6 - Grupo 2 - Monitoreo pipeline churn");

-- ============================================================================
-- Tabla resultados: predicciones exitosas (200 desde el API)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `u6_g02_data_20260919.resultados` (
  run_id STRING NOT NULL OPTIONS(description = "batch_id ISO del DAG run"),
  archivo STRING NOT NULL OPTIONS(description = "nombre del CSV procesado"),
  customer_id STRING NOT NULL,
  fecha_lote DATE OPTIONS(description = "semana del cliente (viene del CSV)"),
  customer_risk_score FLOAT64 NOT NULL,
  predicted_churn BOOL NOT NULL,
  threshold_used FLOAT64 NOT NULL,
  model_version STRING NOT NULL,
  predicted_at TIMESTAMP NOT NULL,
  requested_by STRING,
  loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(loaded_at)
CLUSTER BY archivo, fecha_lote;

-- ============================================================================
-- Tabla cuarentena: filas rechazadas por el API (422) o fallo local
-- ============================================================================
CREATE TABLE IF NOT EXISTS `u6_g02_data_20260919.cuarentena` (
  run_id STRING NOT NULL,
  archivo STRING NOT NULL,
  customer_id STRING,
  fecha_lote DATE,
  http_status INT64 OPTIONS(description = "422, 500, null si fallo antes de POST"),
  error_type STRING NOT NULL OPTIONS(description = "client_side_parse|api_reject|network"),
  error_detail JSON OPTIONS(description = "detalle del error del API"),
  raw JSON NOT NULL OPTIONS(description = "payload crudo tal como venia del CSV"),
  quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(quarantined_at)
CLUSTER BY archivo, error_type;

-- ============================================================================
-- Vista: metricas por corrida
-- ============================================================================
CREATE OR REPLACE VIEW `u6_g02_data_20260919.v_metricas_por_run` AS
SELECT
  r.run_id,
  r.archivo,
  r.fecha_lote,
  COUNTIF(TRUE) AS n_ok,
  (SELECT COUNT(*) FROM `u6_g02_data_20260919.cuarentena` q
     WHERE q.run_id = r.run_id AND q.archivo = r.archivo) AS n_cuarentena,
  AVG(r.customer_risk_score) AS avg_risk,
  COUNTIF(r.predicted_churn) AS n_marca_churn
FROM `u6_g02_data_20260919.resultados` r
GROUP BY r.run_id, r.archivo, r.fecha_lote
ORDER BY r.fecha_lote, r.run_id;
