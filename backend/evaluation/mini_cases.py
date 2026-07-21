"""Twenty closed Chinook cases for the Tahap 3 deterministic demo."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.llm import LanguageCode, LLMIntent, StructuredSQLProposal


class MiniEvaluationCase(BaseModel):
    """Trusted SQL and result identity for one exact demo question."""

    model_config = ConfigDict(frozen=True)

    case_id: str
    question: str
    language: LanguageCode
    sql: str
    tables: tuple[str, ...]
    columns: tuple[str, ...]
    expected_columns: tuple[str, ...]
    expected_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assumptions: tuple[str, ...] = ()

    def proposal(self) -> StructuredSQLProposal:
        return StructuredSQLProposal(
            intent=LLMIntent.ANALYSIS,
            language=self.language,
            needs_clarification=False,
            assumptions=self.assumptions,
            sql=self.sql,
            tables=self.tables,
            columns=self.columns,
            confidence=1.0,
            reasoning_summary="SQL dipilih dari baseline demo terverifikasi."
            if self.language is LanguageCode.INDONESIAN
            else "SQL was selected from the verified demo baseline.",
        )


MINI_EVALUATION_CASES: tuple[MiniEvaluationCase, ...] = (
    MiniEvaluationCase(
        case_id="S3-001",
        question="Berapa jumlah pelanggan?",
        language=LanguageCode.INDONESIAN,
        sql="SELECT COUNT(CustomerId) AS customer_count FROM Customer",
        tables=("Customer",),
        columns=("Customer.CustomerId",),
        expected_columns=("customer_count",),
        expected_result_sha256="3f73b7ad322a5a588c8f4d3e0aa4b873e85eb7c0f9c84d5fc0608a8f950cf932",
    ),
    MiniEvaluationCase(
        case_id="S3-002",
        question="Tampilkan pelanggan yang berasal dari Brasil.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT CustomerId, FirstName, LastName, Country FROM Customer "
            "WHERE Country = 'Brazil' ORDER BY CustomerId"
        ),
        tables=("Customer",),
        columns=(
            "Customer.CustomerId",
            "Customer.FirstName",
            "Customer.LastName",
            "Customer.Country",
        ),
        expected_columns=("CustomerId", "FirstName", "LastName", "Country"),
        expected_result_sha256="f833f527cb63026ee5ea6117caf53658f2acab48689554cd0f48fe0cdf31e539",
    ),
    MiniEvaluationCase(
        case_id="S3-003",
        question="Which employees have the title Sales Support Agent?",
        language=LanguageCode.ENGLISH,
        sql=(
            "SELECT EmployeeId, FirstName, LastName, Title FROM Employee "
            "WHERE Title = 'Sales Support Agent' ORDER BY EmployeeId"
        ),
        tables=("Employee",),
        columns=(
            "Employee.EmployeeId",
            "Employee.FirstName",
            "Employee.LastName",
            "Employee.Title",
        ),
        expected_columns=("EmployeeId", "FirstName", "LastName", "Title"),
        expected_result_sha256="f660cef044f74a5cbafd1bba726f4b18548e4cd86763a555eb01ffff0668075d",
    ),
    MiniEvaluationCase(
        case_id="S3-004",
        question="Tampilkan invoice dengan total lebih dari 10.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT InvoiceId, CustomerId, InvoiceDate, Total FROM Invoice "
            "WHERE Total > 10 ORDER BY InvoiceId"
        ),
        tables=("Invoice",),
        columns=(
            "Invoice.InvoiceId",
            "Invoice.CustomerId",
            "Invoice.InvoiceDate",
            "Invoice.Total",
        ),
        expected_columns=("InvoiceId", "CustomerId", "InvoiceDate", "Total"),
        expected_result_sha256="705da6901765528073efe35222d3d3ae711ba5df0b65cf021658a26631eff828",
    ),
    MiniEvaluationCase(
        case_id="S3-005",
        question="Genre apa saja yang tersedia?",
        language=LanguageCode.INDONESIAN,
        sql="SELECT GenreId, Name FROM Genre ORDER BY Name, GenreId",
        tables=("Genre",),
        columns=("Genre.GenreId", "Genre.Name"),
        expected_columns=("GenreId", "Name"),
        expected_result_sha256="da05f7e442f71c584ed8f016ec71ddb414766098e5340a832f609fd54ebf641f",
    ),
    MiniEvaluationCase(
        case_id="S3-006",
        question="Berapa total nilai seluruh invoice?",
        language=LanguageCode.INDONESIAN,
        sql="SELECT ROUND(SUM(Total), 2) AS total_invoice_value FROM Invoice",
        tables=("Invoice",),
        columns=("Invoice.Total",),
        expected_columns=("total_invoice_value",),
        expected_result_sha256="1aa3818bf795ecaaf80bc052f1c705a636c9b96e8c7b36fe4db53d9e6c700444",
    ),
    MiniEvaluationCase(
        case_id="S3-007",
        question="Berapa rata-rata nilai invoice?",
        language=LanguageCode.INDONESIAN,
        sql="SELECT ROUND(AVG(Total), 2) AS average_invoice_value FROM Invoice",
        tables=("Invoice",),
        columns=("Invoice.Total",),
        expected_columns=("average_invoice_value",),
        expected_result_sha256="16c1103e8f3703d7cd6a5914e1c6bc2e9751db6d0d0a7d2b5e87b73568a6dfc1",
    ),
    MiniEvaluationCase(
        case_id="S3-008",
        question="How many tracks are in each genre?",
        language=LanguageCode.ENGLISH,
        sql=(
            "SELECT g.Name AS genre, COUNT(t.TrackId) AS track_count FROM Genre AS g "
            "LEFT JOIN Track AS t ON t.GenreId = g.GenreId GROUP BY g.GenreId, g.Name "
            "ORDER BY track_count DESC, genre"
        ),
        tables=("Genre", "Track"),
        columns=("Genre.GenreId", "Genre.Name", "Track.TrackId", "Track.GenreId"),
        expected_columns=("genre", "track_count"),
        expected_result_sha256="a0ff8107eff59c90ba2ae916f89e108c475e65ca5dba4905e86e72f28e4390f4",
    ),
    MiniEvaluationCase(
        case_id="S3-009",
        question="Berapa jumlah pelanggan per negara?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT Country, COUNT(CustomerId) AS customer_count FROM Customer "
            "GROUP BY Country ORDER BY customer_count DESC, Country"
        ),
        tables=("Customer",),
        columns=("Customer.Country", "Customer.CustomerId"),
        expected_columns=("Country", "customer_count"),
        expected_result_sha256="881841ef8739561ece77b50c95187b975d2388cdaaca66969960b24a57028176",
    ),
    MiniEvaluationCase(
        case_id="S3-010",
        question="Negara billing mana yang memiliki pendapatan terbesar?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT BillingCountry, ROUND(SUM(Total), 2) AS revenue FROM Invoice "
            "GROUP BY BillingCountry ORDER BY revenue DESC, BillingCountry LIMIT 1"
        ),
        tables=("Invoice",),
        columns=("Invoice.BillingCountry", "Invoice.Total"),
        expected_columns=("BillingCountry", "revenue"),
        expected_result_sha256="66369ec3f621b830d083c0b6a24a77ceab19175075e858a79d93df041a849963",
    ),
    MiniEvaluationCase(
        case_id="S3-011",
        question="Tampilkan lima pelanggan dengan total belanja terbesar.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT c.CustomerId, c.FirstName, c.LastName, ROUND(SUM(i.Total), 2) "
            "AS total_spend FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = "
            "c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY "
            "total_spend DESC, c.CustomerId LIMIT 5"
        ),
        tables=("Customer", "Invoice"),
        columns=(
            "Customer.CustomerId",
            "Customer.FirstName",
            "Customer.LastName",
            "Invoice.CustomerId",
            "Invoice.Total",
        ),
        expected_columns=("CustomerId", "FirstName", "LastName", "total_spend"),
        expected_result_sha256="2989c37f7a0100b93371120af06c30fed9bbaa0510aeb8a33ea86232072d865c",
    ),
    MiniEvaluationCase(
        case_id="S3-012",
        question="Which artist has the most tracks?",
        language=LanguageCode.ENGLISH,
        sql=(
            "SELECT ar.ArtistId, ar.Name, COUNT(t.TrackId) AS track_count FROM Artist "
            "AS ar JOIN Album AS al ON al.ArtistId = ar.ArtistId JOIN Track AS t ON "
            "t.AlbumId = al.AlbumId GROUP BY ar.ArtistId, ar.Name ORDER BY track_count "
            "DESC, ar.ArtistId LIMIT 1"
        ),
        tables=("Artist", "Album", "Track"),
        columns=(
            "Artist.ArtistId",
            "Artist.Name",
            "Album.ArtistId",
            "Album.AlbumId",
            "Track.AlbumId",
            "Track.TrackId",
        ),
        expected_columns=("ArtistId", "Name", "track_count"),
        expected_result_sha256="ccb27a82657cbfb10462ddb876f982143be4526c31deb58ce1086f56f85b16c4",
    ),
    MiniEvaluationCase(
        case_id="S3-013",
        question="Album apa yang memiliki jumlah track terbanyak?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT al.AlbumId, al.Title, COUNT(t.TrackId) AS track_count FROM Album "
            "AS al JOIN Track AS t ON t.AlbumId = al.AlbumId GROUP BY al.AlbumId, "
            "al.Title ORDER BY track_count DESC, al.AlbumId LIMIT 1"
        ),
        tables=("Album", "Track"),
        columns=(
            "Album.AlbumId",
            "Album.Title",
            "Track.AlbumId",
            "Track.TrackId",
        ),
        expected_columns=("AlbumId", "Title", "track_count"),
        expected_result_sha256="298c73abf805ccc93f109c47a0da168b89c5f51cde5005a70737c441fc1d2f37",
    ),
    MiniEvaluationCase(
        case_id="S3-014",
        question="Tampilkan total penjualan per genre.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT g.Name AS genre, ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS "
            "sales FROM InvoiceLine AS il JOIN Track AS t ON t.TrackId = il.TrackId "
            "JOIN Genre AS g ON g.GenreId = t.GenreId GROUP BY g.GenreId, g.Name "
            "ORDER BY sales DESC, genre"
        ),
        tables=("InvoiceLine", "Track", "Genre"),
        columns=(
            "InvoiceLine.UnitPrice",
            "InvoiceLine.Quantity",
            "InvoiceLine.TrackId",
            "Track.TrackId",
            "Track.GenreId",
            "Genre.GenreId",
            "Genre.Name",
        ),
        expected_columns=("genre", "sales"),
        expected_result_sha256="681e3fbc92ecf7f938cfeff4d6853c9188c4bad6160f91ece98fa9a394172260",
        assumptions=("Penjualan dihitung sebagai UnitPrice dikali Quantity.",),
    ),
    MiniEvaluationCase(
        case_id="S3-015",
        question="Karyawan mana yang mendukung pelanggan dengan total belanja tertinggi?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT e.EmployeeId, e.FirstName, e.LastName, ROUND(SUM(i.Total), 2) AS "
            "supported_revenue FROM Employee AS e JOIN Customer AS c ON c.SupportRepId "
            "= e.EmployeeId JOIN Invoice AS i ON i.CustomerId = c.CustomerId GROUP BY "
            "e.EmployeeId, e.FirstName, e.LastName ORDER BY supported_revenue DESC, "
            "e.EmployeeId LIMIT 1"
        ),
        tables=("Employee", "Customer", "Invoice"),
        columns=(
            "Employee.EmployeeId",
            "Employee.FirstName",
            "Employee.LastName",
            "Customer.SupportRepId",
            "Customer.CustomerId",
            "Invoice.CustomerId",
            "Invoice.Total",
        ),
        expected_columns=("EmployeeId", "FirstName", "LastName", "supported_revenue"),
        expected_result_sha256="f65af5d93b7bea8e0aa5a8612bb0e3b4eb3fd9b0159bdd745dccba59c3af5312",
        assumptions=(
            "Karyawan diranking berdasarkan total invoice seluruh pelanggan yang didukung.",
        ),
    ),
    MiniEvaluationCase(
        case_id="S3-016",
        question="Bagaimana tren pendapatan setiap bulan?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT strftime('%Y-%m', InvoiceDate) AS month, ROUND(SUM(Total), 2) AS "
            "revenue FROM Invoice GROUP BY month ORDER BY month"
        ),
        tables=("Invoice",),
        columns=("Invoice.InvoiceDate", "Invoice.Total"),
        expected_columns=("month", "revenue"),
        expected_result_sha256="195c5e22ae921d061195eb48f79ae9445bc98e49960eac4e72fd6c9ac3db2ef4",
    ),
    MiniEvaluationCase(
        case_id="S3-017",
        question="What was the highest-revenue year?",
        language=LanguageCode.ENGLISH,
        sql=(
            "SELECT strftime('%Y', InvoiceDate) AS year, ROUND(SUM(Total), 2) AS revenue "
            "FROM Invoice GROUP BY year ORDER BY revenue DESC, year LIMIT 1"
        ),
        tables=("Invoice",),
        columns=("Invoice.InvoiceDate", "Invoice.Total"),
        expected_columns=("year", "revenue"),
        expected_result_sha256="24383219748e0f715ff45bb12d10ee153e908923d2c6522dc6c502c84ca7c1ba",
    ),
    MiniEvaluationCase(
        case_id="S3-018",
        question="Tampilkan lima invoice terbaru.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT InvoiceId, CustomerId, InvoiceDate, Total FROM Invoice ORDER BY "
            "InvoiceDate DESC, InvoiceId DESC LIMIT 5"
        ),
        tables=("Invoice",),
        columns=(
            "Invoice.InvoiceId",
            "Invoice.CustomerId",
            "Invoice.InvoiceDate",
            "Invoice.Total",
        ),
        expected_columns=("InvoiceId", "CustomerId", "InvoiceDate", "Total"),
        expected_result_sha256="05c92c608940dff8a698df463eda0344a125e2429721913dce299f230baa3a9c",
    ),
    MiniEvaluationCase(
        case_id="S3-019",
        question="Bandingkan jumlah invoice per tahun.",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT strftime('%Y', InvoiceDate) AS year, COUNT(InvoiceId) AS "
            "invoice_count FROM Invoice GROUP BY year ORDER BY year"
        ),
        tables=("Invoice",),
        columns=("Invoice.InvoiceDate", "Invoice.InvoiceId"),
        expected_columns=("year", "invoice_count"),
        expected_result_sha256="8e9bc945756f9126dc907093f76a7ff8775091ab21550d9881ebbfc263245708",
    ),
    MiniEvaluationCase(
        case_id="S3-020",
        question="Siapa sepuluh pelanggan yang paling sering bertransaksi?",
        language=LanguageCode.INDONESIAN,
        sql=(
            "SELECT c.CustomerId, c.FirstName, c.LastName, COUNT(i.InvoiceId) AS "
            "transaction_count FROM Customer AS c JOIN Invoice AS i ON i.CustomerId = "
            "c.CustomerId GROUP BY c.CustomerId, c.FirstName, c.LastName ORDER BY "
            "transaction_count DESC, c.CustomerId LIMIT 10"
        ),
        tables=("Customer", "Invoice"),
        columns=(
            "Customer.CustomerId",
            "Customer.FirstName",
            "Customer.LastName",
            "Invoice.CustomerId",
            "Invoice.InvoiceId",
        ),
        expected_columns=("CustomerId", "FirstName", "LastName", "transaction_count"),
        expected_result_sha256="4b0dafbd1196b06f3bd5125642f876066f8b8a90b1f2e9b940d0d78d57e6ac8f",
    ),
)


def fake_responses() -> dict[str, str]:
    """Return deterministic raw JSON outputs keyed by exact question."""

    return {case.question: case.proposal().model_dump_json() for case in MINI_EVALUATION_CASES}


def find_case(question: str) -> MiniEvaluationCase | None:
    """Find an exact normalized question in the closed catalog."""

    normalized = " ".join(question.casefold().split())
    return next(
        (
            case
            for case in MINI_EVALUATION_CASES
            if " ".join(case.question.casefold().split()) == normalized
        ),
        None,
    )
