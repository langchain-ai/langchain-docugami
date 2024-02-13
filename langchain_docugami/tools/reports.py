import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from langchain_community.tools.sql_database.tool import BaseSQLDatabaseTool
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool


class CustomReportRetrievalTool(BaseSQLDatabaseTool, BaseTool):
    db: SQLDatabase
    assistant_llm: BaseChatModel
    sql_llm: BaseChatModel
    name: str = "query_report"
    description: str = ""

    def _run(
        self,
        query: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:  # type: ignore
        """Use the tool."""
        return f"hello world: {query}"  # replace with sql_result_chain


def report_name_to_report_query_tool_function_name(name: str) -> str:
    """
    Converts a report name to a report query tool function name.

    Report query tool function names follow these conventions:
    1. Retrieval tool function names always start with "query_".
    2. The rest of the name should be a lowercased string, with underscores
       for whitespace.
    3. Exclude any characters other than a-z (lowercase) from the function name,
       replacing them with underscores.
    4. The final function name should not have more than one underscore together.

    >>> report_name_to_report_query_tool_function_name('Earnings Calls')
    'query_earnings_calls'
    >>> report_name_to_report_query_tool_function_name('COVID-19   Statistics')
    'query_covid_19_statistics'
    >>> report_name_to_report_query_tool_function_name('2023 Market Report!!!')
    'query_2023_market_report'
    """
    # Replace non-letter characters with underscores and remove extra whitespaces
    name = re.sub(r"[^a-z\d]", "_", name.lower())
    # Replace whitespace with underscores and remove consecutive underscores
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"_{2,}", "_", name)
    name = name.strip("_")

    return f"query_{name}"


def report_details_to_report_query_tool_description(name: str, table_info: str) -> str:
    """
    Converts a set of chunks to a direct retriever tool description.
    """
    table_info = re.sub(r"\s+", " ", table_info)
    description = (
        f"Given a single input 'query' parameter, runs a SQL query over the {name}"
        + f" report, represented as the following SQL Table:\n\n{table_info}"
    )

    return description[:2048]  # cap to avoid failures when the description is too long


def excel_to_sqlite_connection(
    file_path: Union[Path, str], table_name: str
) -> sqlite3.Connection:
    # Create a temporary SQLite database in memory
    conn = sqlite3.connect(":memory:")

    # Verify the file path
    file_path = Path(file_path)
    if not (file_path.exists() and file_path.suffix.lower() == ".xlsx"):
        raise Exception(f"Invalid file path: {file_path}")

    # Read the Excel file using pandas (only the first sheet)
    df = pd.read_excel(file_path, sheet_name=0)

    # Write the table to the SQLite database
    df.to_sql(table_name, conn, if_exists="replace", index=False)

    return conn


def connect_to_db(
    conn: sqlite3.Connection,
    sample_rows_in_table_info: int = 0,
) -> SQLDatabase:
    temp_db_file = tempfile.NamedTemporaryFile(suffix=".sqlite")
    with sqlite3.connect(temp_db_file.name) as disk_conn:
        conn.backup(disk_conn)  # dumps the connection to disk
    return SQLDatabase.from_uri(
        f"sqlite:///{temp_db_file.name}",
        sample_rows_in_table_info=sample_rows_in_table_info,
    )


def get_retrieval_tool_for_report(
    local_xlsx_path: Path,
    report_name: str,
    retrieval_tool_function_name: str,
    retrieval_tool_description: str,
    assistant_llm: BaseChatModel,
    sql_llm: BaseChatModel,
) -> Optional[BaseTool]:
    if not local_xlsx_path.exists():
        return None

    conn = excel_to_sqlite_connection(local_xlsx_path, report_name)
    db = connect_to_db(conn)

    return CustomReportRetrievalTool(
        db=db,
        assistant_llm=assistant_llm,
        sql_llm=sql_llm,
        name=retrieval_tool_function_name,
        description=retrieval_tool_description,
        return_direct=True,
    )
