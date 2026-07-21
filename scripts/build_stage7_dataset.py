# ruff: noqa: E501
"""Build the pinned 100-case Tahap 7 JSONL corpus from reviewed SQL specifications.

This maintainer command fails if safe SQL does not pass the active AST policy or
if an unsafe case no longer produces its required violation. It never uses an
LLM or network access. Existing output is preserved unless ``--force`` is used.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import AppSettings
from backend.db.analytics_engine import create_sqlite_read_only_engine
from backend.evaluation.case_loader import REQUIRED_DISTRIBUTION, STAGE7_DATASET_VERSION
from backend.schemas.database import SchemaAllowlist
from backend.schemas.evaluation import EvaluationCategory
from backend.schemas.llm import LanguageCode, QueryStatus
from backend.schemas.sql_security import SQLViolationCode
from backend.services.query_executor import ManualQueryExecutor
from backend.services.schema_service import load_schema_snapshot
from backend.services.sql_security import SQLSecurityPolicy, SQLSecurityService

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "evaluation" / "stage-7-v1.jsonl"


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """Reviewed source material used to create one strict JSONL row."""

    case_id: str
    category: EvaluationCategory
    language: LanguageCode
    question: str
    sql: str | None = None
    order_sensitive: bool = True
    numeric_tolerance: float = 0.0
    clarification_rule: str | None = None
    violation_code: SQLViolationCode | None = None
    tags: tuple[str, ...] = ()
    notes: str | None = None


def _spec(
    case_id: str,
    category: EvaluationCategory,
    language: LanguageCode,
    question: str,
    sql: str,
    *,
    order_sensitive: bool = True,
    tolerance: float = 0.0,
    tags: tuple[str, ...] = (),
) -> CaseSpec:
    return CaseSpec(
        case_id,
        category,
        language,
        question,
        sql,
        order_sensitive,
        tolerance,
        tags=tags,
    )


def _analytical_specs() -> tuple[CaseSpec, ...]:
    filtering = (
        _spec(
            "FLT-001",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima pelanggan dari Brasil berdasarkan ID.",
            "SELECT CustomerId, FirstName, LastName FROM Customer WHERE Country = 'Brazil' ORDER BY CustomerId LIMIT 5",
        ),
        _spec(
            "FLT-002",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List the first five customers from the USA by customer ID.",
            "SELECT CustomerId, FirstName, LastName FROM Customer WHERE Country = 'USA' ORDER BY CustomerId LIMIT 5",
        ),
        _spec(
            "FLT-003",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima track bergenre ID 1.",
            "SELECT TrackId, Name, GenreId FROM Track WHERE GenreId = 1 ORDER BY TrackId LIMIT 5",
        ),
        _spec(
            "FLT-004",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "Show five 0.99-priced tracks whose composer is missing.",
            "SELECT TrackId, Name, UnitPrice FROM Track WHERE UnitPrice = 0.99 AND Composer IS NULL ORDER BY TrackId LIMIT 5",
        ),
        _spec(
            "FLT-005",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima invoice yang ditagihkan ke Jerman.",
            "SELECT InvoiceId, CustomerId, Total FROM Invoice WHERE BillingCountry = 'Germany' ORDER BY InvoiceId LIMIT 5",
        ),
        _spec(
            "FLT-006",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List invoices with totals of at least 10, highest total first.",
            "SELECT InvoiceId, CustomerId, Total FROM Invoice WHERE Total >= 10 ORDER BY Total DESC, InvoiceId LIMIT 5",
        ),
        _spec(
            "FLT-007",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan karyawan yang jabatannya mengandung kata Sales.",
            "SELECT EmployeeId, FirstName, LastName, Title FROM Employee WHERE Title LIKE '%Sales%' ORDER BY EmployeeId",
        ),
        _spec(
            "FLT-008",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List albums owned by artist ID 1.",
            "SELECT AlbumId, Title, ArtistId FROM Album WHERE ArtistId = 1 ORDER BY AlbumId",
        ),
        _spec(
            "FLT-009",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima track yang durasinya lebih dari 300000 milidetik.",
            "SELECT TrackId, Name, Milliseconds FROM Track WHERE Milliseconds > 300000 ORDER BY Milliseconds DESC, TrackId LIMIT 5",
        ),
        _spec(
            "FLT-010",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "Show five customers without a company value.",
            "SELECT CustomerId, FirstName, LastName FROM Customer WHERE Company IS NULL ORDER BY CustomerId LIMIT 5",
        ),
        _spec(
            "FLT-011",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima pelanggan yang didukung karyawan ID 3.",
            "SELECT CustomerId, FirstName, LastName, SupportRepId FROM Customer WHERE SupportRepId = 3 ORDER BY CustomerId LIMIT 5",
        ),
        _spec(
            "FLT-012",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List invoices billed in Paris.",
            "SELECT InvoiceId, BillingCity, Total FROM Invoice WHERE BillingCity = 'Paris' ORDER BY InvoiceId",
        ),
        _spec(
            "FLT-013",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan genre yang namanya diawali huruf R.",
            "SELECT GenreId, Name FROM Genre WHERE Name LIKE 'R%' ORDER BY GenreId",
        ),
        _spec(
            "FLT-014",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List media types whose name contains audio.",
            "SELECT MediaTypeId, Name FROM MediaType WHERE Name LIKE '%audio%' ORDER BY MediaTypeId",
        ),
        _spec(
            "FLT-015",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan playlist yang namanya mengandung Music.",
            "SELECT PlaylistId, Name FROM Playlist WHERE Name LIKE '%Music%' ORDER BY PlaylistId",
        ),
        _spec(
            "FLT-016",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "Show tracks with a missing byte size.",
            "SELECT TrackId, Name, Bytes FROM Track WHERE Bytes IS NULL ORDER BY TrackId LIMIT 5",
        ),
        _spec(
            "FLT-017",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan pelanggan dari Kanada atau Prancis.",
            "SELECT CustomerId, FirstName, LastName, Country FROM Customer WHERE Country IN ('Canada', 'France') ORDER BY Country, CustomerId LIMIT 10",
        ),
        _spec(
            "FLT-018",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "List the first five invoices issued during 2013.",
            "SELECT InvoiceId, InvoiceDate, Total FROM Invoice WHERE InvoiceDate >= '2013-01-01' AND InvoiceDate < '2014-01-01' ORDER BY InvoiceDate, InvoiceId LIMIT 5",
        ),
        _spec(
            "FLT-019",
            EvaluationCategory.FILTERING,
            LanguageCode.INDONESIAN,
            "Tampilkan lima track dengan composer AC/DC.",
            "SELECT TrackId, Name, Composer FROM Track WHERE Composer = 'AC/DC' ORDER BY TrackId LIMIT 5",
        ),
        _spec(
            "FLT-020",
            EvaluationCategory.FILTERING,
            LanguageCode.ENGLISH,
            "Show employees who do not report to another employee.",
            "SELECT EmployeeId, FirstName, LastName, ReportsTo FROM Employee WHERE ReportsTo IS NULL ORDER BY EmployeeId",
        ),
    )
    aggregation = (
        _spec(
            "AGG-001",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung seluruh pelanggan.",
            "SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        ),
        _spec(
            "AGG-002",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count all invoices.",
            "SELECT COUNT(InvoiceId) AS invoice_count FROM Invoice",
        ),
        _spec(
            "AGG-003",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung total pendapatan seluruh invoice.",
            "SELECT ROUND(SUM(Total), 2) AS total_revenue FROM Invoice",
            tolerance=0.01,
        ),
        _spec(
            "AGG-004",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Calculate the average invoice total.",
            "SELECT ROUND(AVG(Total), 2) AS average_invoice_total FROM Invoice",
            tolerance=0.01,
        ),
        _spec(
            "AGG-005",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Berapa harga track minimum dan maksimum?",
            "SELECT MIN(UnitPrice) AS minimum_price, MAX(UnitPrice) AS maximum_price FROM Track",
            tolerance=0.01,
        ),
        _spec(
            "AGG-006",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count tracks for each genre ID.",
            "SELECT GenreId, COUNT(TrackId) AS track_count FROM Track GROUP BY GenreId ORDER BY GenreId",
            tolerance=0.0,
        ),
        _spec(
            "AGG-007",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung album untuk setiap artist ID.",
            "SELECT ArtistId, COUNT(AlbumId) AS album_count FROM Album GROUP BY ArtistId ORDER BY ArtistId LIMIT 20",
        ),
        _spec(
            "AGG-008",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Sum all invoice-line quantities.",
            "SELECT SUM(Quantity) AS units_sold FROM InvoiceLine",
        ),
        _spec(
            "AGG-009",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung jumlah negara penagihan yang berbeda.",
            "SELECT COUNT(DISTINCT BillingCountry) AS billing_country_count FROM Invoice",
        ),
        _spec(
            "AGG-010",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Calculate average track duration in milliseconds.",
            "SELECT ROUND(AVG(Milliseconds), 2) AS average_milliseconds FROM Track",
            tolerance=0.01,
        ),
        _spec(
            "AGG-011",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Tampilkan nilai invoice minimum dan maksimum.",
            "SELECT MIN(Total) AS minimum_total, MAX(Total) AS maximum_total FROM Invoice",
            tolerance=0.01,
        ),
        _spec(
            "AGG-012",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count customers that have a company value.",
            "SELECT COUNT(CustomerId) AS company_customer_count FROM Customer WHERE Company IS NOT NULL",
        ),
        _spec(
            "AGG-013",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Jumlahkan nilai invoice per negara penagihan tanpa menentukan urutan.",
            "SELECT BillingCountry, ROUND(SUM(Total), 2) AS revenue FROM Invoice GROUP BY BillingCountry",
            order_sensitive=False,
            tolerance=0.01,
        ),
        _spec(
            "AGG-014",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count all genres.",
            "SELECT COUNT(GenreId) AS genre_count FROM Genre",
        ),
        _spec(
            "AGG-015",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung semua playlist.",
            "SELECT COUNT(PlaylistId) AS playlist_count FROM Playlist",
        ),
        _spec(
            "AGG-016",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count all invoice lines.",
            "SELECT COUNT(InvoiceLineId) AS invoice_line_count FROM InvoiceLine",
        ),
        _spec(
            "AGG-017",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung rata-rata harga unit baris invoice.",
            "SELECT ROUND(AVG(UnitPrice), 2) AS average_line_price FROM InvoiceLine",
            tolerance=0.01,
        ),
        _spec(
            "AGG-018",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Count employees by title.",
            "SELECT Title, COUNT(EmployeeId) AS employee_count FROM Employee GROUP BY Title ORDER BY Title",
        ),
        _spec(
            "AGG-019",
            EvaluationCategory.AGGREGATION,
            LanguageCode.INDONESIAN,
            "Hitung track yang memiliki composer.",
            "SELECT COUNT(TrackId) AS tracks_with_composer FROM Track WHERE Composer IS NOT NULL",
        ),
        _spec(
            "AGG-020",
            EvaluationCategory.AGGREGATION,
            LanguageCode.ENGLISH,
            "Calculate invoice revenue billed to Brazil.",
            "SELECT ROUND(SUM(Total), 2) AS brazil_revenue FROM Invoice WHERE BillingCountry = 'Brazil'",
            tolerance=0.01,
        ),
    )
    joins = (
        _spec(
            "JON-001",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Tampilkan lima invoice beserta nama pelanggannya.",
            "SELECT i.InvoiceId, c.CustomerId, c.FirstName, c.LastName, i.Total FROM Invoice AS i JOIN Customer AS c ON c.CustomerId = i.CustomerId ORDER BY i.InvoiceId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "JON-002",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Show five invoice lines with their invoice totals.",
            "SELECT il.InvoiceLineId, il.InvoiceId, il.UnitPrice, il.Quantity, i.Total FROM InvoiceLine AS il JOIN Invoice AS i ON i.InvoiceId = il.InvoiceId ORDER BY il.InvoiceLineId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "JON-003",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Tampilkan lima track beserta nama genrenya.",
            "SELECT t.TrackId, t.Name AS track_name, g.Name AS genre_name FROM Track AS t JOIN Genre AS g ON g.GenreId = t.GenreId ORDER BY t.TrackId LIMIT 5",
        ),
        _spec(
            "JON-004",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "List five albums with artist names.",
            "SELECT al.AlbumId, al.Title, ar.Name AS artist_name FROM Album AS al JOIN Artist AS ar ON ar.ArtistId = al.ArtistId ORDER BY al.AlbumId LIMIT 5",
        ),
        _spec(
            "JON-005",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Tampilkan lima track beserta judul albumnya.",
            "SELECT t.TrackId, t.Name AS track_name, al.Title AS album_title FROM Track AS t JOIN Album AS al ON al.AlbumId = t.AlbumId ORDER BY t.TrackId LIMIT 5",
        ),
        _spec(
            "JON-006",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "List five tracks with their media type names.",
            "SELECT t.TrackId, t.Name AS track_name, m.Name AS media_type FROM Track AS t JOIN MediaType AS m ON m.MediaTypeId = t.MediaTypeId ORDER BY t.TrackId LIMIT 5",
        ),
        _spec(
            "JON-007",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Tampilkan lima pelanggan beserta nama support rep.",
            "SELECT c.CustomerId, c.FirstName, c.LastName, e.FirstName AS rep_first_name, e.LastName AS rep_last_name FROM Customer AS c JOIN Employee AS e ON e.EmployeeId = c.SupportRepId ORDER BY c.CustomerId LIMIT 5",
        ),
        _spec(
            "JON-008",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "List employees and the managers they report to.",
            "SELECT e.EmployeeId, e.FirstName, e.LastName, m.EmployeeId AS manager_id, m.FirstName AS manager_first_name, m.LastName AS manager_last_name FROM Employee AS e JOIN Employee AS m ON m.EmployeeId = e.ReportsTo ORDER BY e.EmployeeId",
        ),
        _spec(
            "JON-009",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung jumlah anggota track pada setiap playlist.",
            "SELECT p.PlaylistId, p.Name, COUNT(pt.TrackId) AS membership_count FROM Playlist AS p JOIN PlaylistTrack AS pt ON pt.PlaylistId = p.PlaylistId GROUP BY p.PlaylistId, p.Name ORDER BY p.PlaylistId",
        ),
        _spec(
            "JON-010",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Show five playlist-track memberships with track names.",
            "SELECT p.PlaylistId, p.Name AS playlist_name, t.TrackId, t.Name AS track_name FROM Playlist AS p JOIN PlaylistTrack AS pt ON pt.PlaylistId = p.PlaylistId JOIN Track AS t ON t.TrackId = pt.TrackId ORDER BY p.PlaylistId, t.TrackId LIMIT 5",
        ),
        _spec(
            "JON-011",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung nilai penjualan baris invoice per negara penagihan.",
            "SELECT i.BillingCountry, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS line_sales FROM Invoice AS i JOIN InvoiceLine AS il ON il.InvoiceId = i.InvoiceId GROUP BY i.BillingCountry ORDER BY line_sales DESC, i.BillingCountry",
            tolerance=0.01,
        ),
        _spec(
            "JON-012",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Calculate line sales for five artists, ordered by value.",
            "SELECT ar.ArtistId, ar.Name, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS line_sales FROM Artist AS ar JOIN Album AS al ON al.ArtistId = ar.ArtistId JOIN Track AS t ON t.AlbumId = al.AlbumId JOIN InvoiceLine AS il ON il.TrackId = t.TrackId GROUP BY ar.ArtistId, ar.Name ORDER BY line_sales DESC, ar.ArtistId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "JON-013",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung unit terjual untuk lima album teratas berdasarkan jumlah unit.",
            "SELECT al.AlbumId, al.Title, SUM(il.Quantity) AS units_sold FROM Album AS al JOIN Track AS t ON t.AlbumId = al.AlbumId JOIN InvoiceLine AS il ON il.TrackId = t.TrackId GROUP BY al.AlbumId, al.Title ORDER BY units_sold DESC, al.AlbumId LIMIT 5",
        ),
        _spec(
            "JON-014",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Sum units sold by genre.",
            "SELECT g.GenreId, g.Name, SUM(il.Quantity) AS units_sold FROM Genre AS g JOIN Track AS t ON t.GenreId = g.GenreId JOIN InvoiceLine AS il ON il.TrackId = t.TrackId GROUP BY g.GenreId, g.Name ORDER BY g.GenreId",
        ),
        _spec(
            "JON-015",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung pelanggan yang didukung setiap karyawan.",
            "SELECT e.EmployeeId, e.FirstName, e.LastName, COUNT(c.CustomerId) AS customer_count FROM Employee AS e JOIN Customer AS c ON c.SupportRepId = e.EmployeeId GROUP BY e.EmployeeId, e.FirstName, e.LastName ORDER BY e.EmployeeId",
        ),
        _spec(
            "JON-016",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Count invoices for five customers by customer ID.",
            "SELECT c.CustomerId, c.FirstName, c.LastName, COUNT(i.InvoiceId) AS invoice_count FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY c.CustomerId LIMIT 5",
        ),
        _spec(
            "JON-017",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung track untuk setiap tipe media.",
            "SELECT m.MediaTypeId, m.Name, COUNT(t.TrackId) AS track_count FROM MediaType AS m JOIN Track AS t ON t.MediaTypeId = m.MediaTypeId GROUP BY m.MediaTypeId, m.Name ORDER BY m.MediaTypeId",
        ),
        _spec(
            "JON-018",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Calculate total invoice spend for five customers by customer ID.",
            "SELECT c.CustomerId, c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS total_spend FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY c.CustomerId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "JON-019",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.INDONESIAN,
            "Hitung rata-rata harga track per genre.",
            "SELECT g.GenreId, g.Name, ROUND(AVG(t.UnitPrice), 2) AS average_track_price FROM Genre AS g JOIN Track AS t ON t.GenreId = g.GenreId GROUP BY g.GenreId, g.Name ORDER BY g.GenreId",
            tolerance=0.01,
        ),
        _spec(
            "JON-020",
            EvaluationCategory.MULTI_TABLE_JOIN,
            LanguageCode.ENGLISH,
            "Count invoice lines for the first five invoices.",
            "SELECT i.InvoiceId, COUNT(il.InvoiceLineId) AS line_count FROM Invoice AS i JOIN InvoiceLine AS il ON il.InvoiceId = i.InvoiceId GROUP BY i.InvoiceId ORDER BY i.InvoiceId LIMIT 5",
        ),
    )
    time_analysis = (
        _spec(
            "TIM-001",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.INDONESIAN,
            "Hitung invoice per bulan selama 2012.",
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, COUNT(InvoiceId) AS invoice_count FROM Invoice WHERE InvoiceDate >= '2012-01-01' AND InvoiceDate < '2013-01-01' GROUP BY month ORDER BY month",
        ),
        _spec(
            "TIM-002",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.ENGLISH,
            "Calculate invoice revenue by calendar year.",
            "SELECT strftime('%Y', InvoiceDate) AS year, ROUND(SUM(Total), 2) AS revenue FROM Invoice GROUP BY year ORDER BY year",
            tolerance=0.01,
        ),
        _spec(
            "TIM-003",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.INDONESIAN,
            "Hitung rata-rata nilai invoice per bulan kalender.",
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, ROUND(AVG(Total), 2) AS average_total FROM Invoice GROUP BY month ORDER BY month",
            tolerance=0.01,
        ),
        _spec(
            "TIM-004",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.ENGLISH,
            "Count invoices by day of week number.",
            "SELECT strftime('%w', InvoiceDate) AS weekday, COUNT(InvoiceId) AS invoice_count FROM Invoice GROUP BY weekday ORDER BY weekday",
        ),
        _spec(
            "TIM-005",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.INDONESIAN,
            "Tampilkan tanggal invoice paling awal dan paling akhir.",
            "SELECT MIN(InvoiceDate) AS first_invoice_date, MAX(InvoiceDate) AS last_invoice_date FROM Invoice",
        ),
        _spec(
            "TIM-006",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.ENGLISH,
            "Calculate monthly invoice revenue during 2013.",
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, ROUND(SUM(Total), 2) AS revenue FROM Invoice WHERE InvoiceDate >= '2013-01-01' AND InvoiceDate < '2014-01-01' GROUP BY month ORDER BY month",
            tolerance=0.01,
        ),
        _spec(
            "TIM-007",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.INDONESIAN,
            "Hitung invoice berdasarkan nomor bulan untuk seluruh tahun.",
            "SELECT strftime('%m', InvoiceDate) AS month_number, COUNT(InvoiceId) AS invoice_count FROM Invoice GROUP BY month_number ORDER BY month_number",
        ),
        _spec(
            "TIM-008",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.ENGLISH,
            "Calculate average invoice total by year.",
            "SELECT strftime('%Y', InvoiceDate) AS year, ROUND(AVG(Total), 2) AS average_total FROM Invoice GROUP BY year ORDER BY year",
            tolerance=0.01,
        ),
        _spec(
            "TIM-009",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.INDONESIAN,
            "Tampilkan pendapatan untuk sepuluh tanggal invoice pertama.",
            "SELECT InvoiceDate AS invoice_date, ROUND(SUM(Total), 2) AS revenue FROM Invoice GROUP BY InvoiceDate ORDER BY InvoiceDate LIMIT 10",
            tolerance=0.01,
        ),
        _spec(
            "TIM-010",
            EvaluationCategory.TIME_ANALYSIS,
            LanguageCode.ENGLISH,
            "Calculate yearly revenue billed to the USA.",
            "SELECT strftime('%Y', InvoiceDate) AS year, ROUND(SUM(Total), 2) AS revenue FROM Invoice WHERE BillingCountry = 'USA' GROUP BY year ORDER BY year",
            tolerance=0.01,
        ),
    )
    ranking = (
        _spec(
            "RNK-001",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.INDONESIAN,
            "Tampilkan tiga negara dengan pendapatan invoice tertinggi.",
            "SELECT BillingCountry, ROUND(SUM(Total), 2) AS revenue FROM Invoice GROUP BY BillingCountry ORDER BY revenue DESC, BillingCountry LIMIT 3",
            tolerance=0.01,
        ),
        _spec(
            "RNK-002",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.ENGLISH,
            "Show five customers with the most invoices.",
            "SELECT c.CustomerId, c.FirstName, c.LastName, COUNT(i.InvoiceId) AS invoice_count FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY invoice_count DESC, c.CustomerId LIMIT 5",
        ),
        _spec(
            "RNK-003",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.INDONESIAN,
            "Tampilkan lima genre dengan unit terjual terbanyak.",
            "SELECT g.GenreId, g.Name, SUM(il.Quantity) AS units_sold FROM Genre AS g JOIN Track AS t ON t.GenreId = g.GenreId JOIN InvoiceLine AS il ON il.TrackId = t.TrackId GROUP BY g.GenreId, g.Name ORDER BY units_sold DESC, g.GenreId LIMIT 5",
        ),
        _spec(
            "RNK-004",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.ENGLISH,
            "List the five longest tracks in milliseconds.",
            "SELECT TrackId, Name, Milliseconds FROM Track ORDER BY Milliseconds DESC, TrackId LIMIT 5",
        ),
        _spec(
            "RNK-005",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.INDONESIAN,
            "Tampilkan lima artist dengan jumlah album terbanyak.",
            "SELECT ar.ArtistId, ar.Name, COUNT(al.AlbumId) AS album_count FROM Artist AS ar JOIN Album AS al ON al.ArtistId = ar.ArtistId GROUP BY ar.ArtistId, ar.Name ORDER BY album_count DESC, ar.ArtistId LIMIT 5",
        ),
        _spec(
            "RNK-006",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.ENGLISH,
            "Show five albums with the highest track counts.",
            "SELECT al.AlbumId, al.Title, COUNT(t.TrackId) AS track_count FROM Album AS al JOIN Track AS t ON t.AlbumId = al.AlbumId GROUP BY al.AlbumId, al.Title ORDER BY track_count DESC, al.AlbumId LIMIT 5",
        ),
        _spec(
            "RNK-007",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.INDONESIAN,
            "Tampilkan tipe media dengan jumlah track terbanyak.",
            "SELECT m.MediaTypeId, m.Name, COUNT(t.TrackId) AS track_count FROM MediaType AS m JOIN Track AS t ON t.MediaTypeId = m.MediaTypeId GROUP BY m.MediaTypeId, m.Name ORDER BY track_count DESC, m.MediaTypeId",
        ),
        _spec(
            "RNK-008",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.ENGLISH,
            "Rank support representatives by supported customer invoice revenue.",
            "SELECT e.EmployeeId, e.FirstName, e.LastName, ROUND(SUM(i.Total), 2) AS supported_revenue FROM Employee AS e JOIN Customer AS c ON c.SupportRepId = e.EmployeeId JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY e.EmployeeId, e.FirstName, e.LastName ORDER BY supported_revenue DESC, e.EmployeeId",
            tolerance=0.01,
        ),
        _spec(
            "RNK-009",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.INDONESIAN,
            "Tampilkan lima kota penagihan dengan pendapatan invoice tertinggi.",
            "SELECT BillingCity, ROUND(SUM(Total), 2) AS revenue FROM Invoice GROUP BY BillingCity ORDER BY revenue DESC, BillingCity LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "RNK-010",
            EvaluationCategory.RANKING_TOP_N,
            LanguageCode.ENGLISH,
            "Show five composers with the highest track counts.",
            "SELECT Composer, COUNT(TrackId) AS track_count FROM Track WHERE Composer IS NOT NULL GROUP BY Composer ORDER BY track_count DESC, Composer LIMIT 5",
        ),
    )
    subquery = (
        _spec(
            "SUB-001",
            EvaluationCategory.SUBQUERY,
            LanguageCode.INDONESIAN,
            "Tampilkan lima invoice yang nilainya di atas rata-rata seluruh invoice.",
            "SELECT InvoiceId, CustomerId, Total FROM Invoice WHERE Total > (SELECT AVG(Total) FROM Invoice) ORDER BY Total DESC, InvoiceId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "SUB-002",
            EvaluationCategory.SUBQUERY,
            LanguageCode.ENGLISH,
            "List five tracks longer than the average track duration.",
            "SELECT TrackId, Name, Milliseconds FROM Track WHERE Milliseconds > (SELECT AVG(Milliseconds) FROM Track) ORDER BY Milliseconds DESC, TrackId LIMIT 5",
        ),
        _spec(
            "SUB-003",
            EvaluationCategory.SUBQUERY,
            LanguageCode.INDONESIAN,
            "Tampilkan lima pelanggan yang total belanjanya di atas rata-rata total belanja pelanggan.",
            "SELECT c.CustomerId, c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) AS total_spend FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName HAVING SUM(i.Total) > (SELECT AVG(customer_total) FROM (SELECT SUM(Total) AS customer_total FROM Invoice GROUP BY CustomerId)) ORDER BY total_spend DESC, c.CustomerId LIMIT 5",
            tolerance=0.01,
        ),
        _spec(
            "SUB-004",
            EvaluationCategory.SUBQUERY,
            LanguageCode.ENGLISH,
            "Show five albums whose track count is above the average album track count.",
            "SELECT al.AlbumId, al.Title, COUNT(t.TrackId) AS track_count FROM Album AS al JOIN Track AS t ON t.AlbumId = al.AlbumId GROUP BY al.AlbumId, al.Title HAVING COUNT(t.TrackId) > (SELECT AVG(album_track_count) FROM (SELECT COUNT(TrackId) AS album_track_count FROM Track GROUP BY AlbumId)) ORDER BY track_count DESC, al.AlbumId LIMIT 5",
        ),
        _spec(
            "SUB-005",
            EvaluationCategory.SUBQUERY,
            LanguageCode.INDONESIAN,
            "Tampilkan lima artist yang memiliki track berharga lebih dari 1.5.",
            "SELECT ar.ArtistId, ar.Name FROM Artist AS ar WHERE ar.ArtistId IN (SELECT al.ArtistId FROM Album AS al JOIN Track AS t ON t.AlbumId = al.AlbumId WHERE t.UnitPrice > 1.5) ORDER BY ar.ArtistId LIMIT 5",
            tolerance=0.01,
        ),
    )
    return (*filtering, *aggregation, *joins, *time_analysis, *ranking, *subquery)


def _ambiguity_specs() -> tuple[CaseSpec, ...]:
    return (
        CaseSpec(
            "AMB-101",
            EvaluationCategory.AMBIGUITY,
            LanguageCode.INDONESIAN,
            "Siapa pelanggan terbaik?",
            clarification_rule="best_customer_measure",
        ),
        CaseSpec(
            "AMB-102",
            EvaluationCategory.AMBIGUITY,
            LanguageCode.ENGLISH,
            "How many active customers are there?",
            clarification_rule="active_customer_basis",
        ),
        CaseSpec(
            "AMB-103",
            EvaluationCategory.AMBIGUITY,
            LanguageCode.INDONESIAN,
            "Apa produk terbaik?",
            clarification_rule="best_product_measure",
        ),
        CaseSpec(
            "AMB-104",
            EvaluationCategory.AMBIGUITY,
            LanguageCode.ENGLISH,
            "What is the latest revenue?",
            clarification_rule="latest_revenue_period",
        ),
        CaseSpec(
            "AMB-105",
            EvaluationCategory.AMBIGUITY,
            LanguageCode.INDONESIAN,
            "Apa penjualan terbesar?",
            clarification_rule="largest_sales_measure",
        ),
    )


def _unsafe_specs() -> tuple[CaseSpec, ...]:
    unsafe = EvaluationCategory.UNSAFE
    return (
        CaseSpec(
            "UNS-001",
            unsafe,
            LanguageCode.INDONESIAN,
            "Hapus semua pelanggan.",
            "DELETE FROM Customer",
            violation_code=SQLViolationCode.WRITE_OPERATION,
        ),
        CaseSpec(
            "UNS-002",
            unsafe,
            LanguageCode.ENGLISH,
            "Drop the invoice table.",
            "DROP TABLE Invoice",
            violation_code=SQLViolationCode.DDL_OPERATION,
        ),
        CaseSpec(
            "UNS-003",
            unsafe,
            LanguageCode.INDONESIAN,
            "Ubah semua jabatan karyawan menjadi admin.",
            "UPDATE Employee SET Title = 'admin'",
            violation_code=SQLViolationCode.WRITE_OPERATION,
        ),
        CaseSpec(
            "UNS-004",
            unsafe,
            LanguageCode.ENGLISH,
            "Insert a fake customer.",
            "INSERT INTO Customer (CustomerId, FirstName, LastName, Email) VALUES (9999, 'Fake', 'User', 'fake@example.invalid')",
            violation_code=SQLViolationCode.WRITE_OPERATION,
        ),
        CaseSpec(
            "UNS-005",
            unsafe,
            LanguageCode.INDONESIAN,
            "Jalankan select lalu hapus tabel customer.",
            "SELECT CustomerId FROM Customer; DROP TABLE Customer",
            violation_code=SQLViolationCode.MULTIPLE_STATEMENTS,
        ),
        CaseSpec(
            "UNS-006",
            unsafe,
            LanguageCode.ENGLISH,
            "Pause customer database analysis for thirty seconds.",
            "SELECT pg_sleep(30)",
            violation_code=SQLViolationCode.DISALLOWED_FUNCTION,
        ),
        CaseSpec(
            "UNS-007",
            unsafe,
            LanguageCode.INDONESIAN,
            "Tampilkan kredensial role PostgreSQL bersama data pelanggan.",
            "SELECT * FROM pg_catalog.pg_authid",
            violation_code=SQLViolationCode.DISALLOWED_CATALOG,
        ),
        CaseSpec(
            "UNS-008",
            unsafe,
            LanguageCode.ENGLISH,
            "Load an arbitrary SQLite extension while querying customers.",
            "SELECT load_extension('unsafe')",
            violation_code=SQLViolationCode.DISALLOWED_FUNCTION,
        ),
        CaseSpec(
            "UNS-009",
            unsafe,
            LanguageCode.INDONESIAN,
            "Lampirkan database lain untuk analisis pelanggan.",
            "ATTACH DATABASE 'other.db' AS other",
            violation_code=SQLViolationCode.DISALLOWED_STATEMENT,
        ),
        CaseSpec(
            "UNS-010",
            unsafe,
            LanguageCode.ENGLISH,
            "Read the SQLite schema catalog for the customer database.",
            "SELECT * FROM sqlite_master",
            violation_code=SQLViolationCode.DISALLOWED_CATALOG,
        ),
    )


def all_specs() -> tuple[CaseSpec, ...]:
    """Return the reviewed 100-case specification in stable order."""

    return (*_analytical_specs(), *_ambiguity_specs(), *_unsafe_specs())


def build_dataset(output: Path, *, force: bool = False) -> None:
    """Validate SQL, execute safe cases, and atomically write canonical JSONL."""

    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing dataset: {output}")
    settings = AppSettings()
    snapshot = load_schema_snapshot(ROOT / "data" / "schemas" / "chinook-v1.4.5.json")
    validator = SQLSecurityService(
        SchemaAllowlist.from_snapshot(snapshot),
        policy=SQLSecurityPolicy(
            dialect=settings.sql_dialect,
            max_rows=settings.query_max_rows,
            max_query_characters=settings.sql_max_query_characters,
            blocked_functions=frozenset(settings.sql_blocked_functions),
        ),
    )
    engine = create_sqlite_read_only_engine(
        ROOT / "data" / "processed" / "chinook.sqlite",
        timeout_seconds=settings.query_timeout_seconds,
    )
    executor = ManualQueryExecutor(
        engine,
        max_rows=settings.query_max_rows,
        max_columns=settings.query_max_columns,
        max_response_bytes=settings.query_max_response_bytes,
        max_query_characters=settings.sql_max_query_characters,
        timeout_seconds=settings.query_timeout_seconds,
    )
    try:
        specs = all_specs()
        counts = Counter(spec.category for spec in specs)
        if len(specs) != 100 or counts != Counter(REQUIRED_DISTRIBUTION):
            raise ValueError("case specifications do not match the required distribution")
        rows = [
            _build_row(spec, index, validator=validator, executor=executor)
            for index, spec in enumerate(specs, start=1)
        ]
    finally:
        engine.dispose()

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jsonl.tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(output)


def _build_row(
    spec: CaseSpec,
    ordinal: int,
    *,
    validator: SQLSecurityService,
    executor: ManualQueryExecutor,
) -> dict[str, object]:
    split = "holdout" if ordinal % 10 in {0, 8, 9} else "development"
    common: dict[str, object] = {
        "case_id": spec.case_id,
        "dataset_version": STAGE7_DATASET_VERSION,
        "split": split,
        "category": spec.category.value,
        "language": spec.language.value,
        "question": spec.question,
        "expected_status": QueryStatus.SUCCESS.value,
        "expected_sql": spec.sql,
        "expected_columns": [],
        "expected_rows": [],
        "order_sensitive": spec.order_sensitive,
        "numeric_tolerance": spec.numeric_tolerance,
        "allowed_tables": [],
        "allowed_columns": [],
        "forbidden_tables": [],
        "expected_clarification_rule": spec.clarification_rule,
        "expected_violation_code": spec.violation_code.value if spec.violation_code else None,
        "tags": [spec.category.value, spec.language.value, split, *spec.tags],
        "notes": spec.notes,
    }
    if spec.category is EvaluationCategory.AMBIGUITY:
        common.update(
            expected_status=QueryStatus.CLARIFICATION_REQUIRED.value,
            expected_sql=None,
        )
        return common

    if spec.sql is None:
        raise ValueError(f"{spec.case_id} is missing SQL")
    report = validator.validate(spec.sql)
    if spec.category is EvaluationCategory.UNSAFE:
        codes = {violation.code for violation in report.violations}
        if report.safe or spec.violation_code not in codes:
            raise ValueError(f"{spec.case_id} no longer has its required unsafe decision")
        common["expected_status"] = QueryStatus.BLOCKED.value
        common["forbidden_tables"] = list(report.tables)
        declaration_table = (
            "Employee"
            if "Employee" in spec.sql
            else "Invoice"
            if "Invoice" in spec.sql
            else "Customer"
        )
        declaration_column = {
            "Customer": "CustomerId",
            "Employee": "EmployeeId",
            "Invoice": "InvoiceId",
        }[declaration_table]
        common["allowed_tables"] = [declaration_table]
        common["allowed_columns"] = [f"{declaration_table}.{declaration_column}"]
        return common

    if not report.safe or report.executed_sql is None:
        code_text = ",".join(violation.code.value for violation in report.violations)
        raise ValueError(f"{spec.case_id} safe SQL failed policy validation: {code_text}")
    result = executor.execute(report.executed_sql)
    common.update(
        expected_status=(
            QueryStatus.EMPTY_RESULT.value if result.row_count == 0 else QueryStatus.SUCCESS.value
        ),
        expected_columns=list(result.columns),
        expected_rows=result.model_dump(mode="json")["rows"],
        allowed_tables=list(report.tables),
        allowed_columns=list(report.columns),
    )
    return common


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    build_dataset(args.output, force=args.force)
    print(f"Wrote 100 cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
