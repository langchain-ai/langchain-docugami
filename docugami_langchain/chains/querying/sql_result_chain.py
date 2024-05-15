import logging
from operator import itemgetter
from typing import AsyncIterator, Optional

from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.example_selectors import MaxMarginalRelevanceExampleSelector
from langchain_core.runnables import Runnable, RunnableConfig, RunnableLambda
from sqlglot import ParseError

from docugami_langchain.base_runnable import TracedResponse
from docugami_langchain.chains.base import BaseDocugamiChain
from docugami_langchain.chains.querying.models import ExplainedSQLResult
from docugami_langchain.chains.querying.sql_fixup_chain import SQLFixupChain
from docugami_langchain.output_parsers.sql_finding import SQLFindingOutputParser
from docugami_langchain.output_parsers.text_cleaning import TextCleaningOutputParser
from docugami_langchain.params import RunnableParameters, RunnableSingleParameter
from docugami_langchain.utils.sql import (
    check_and_format_query,
    create_example_selector,
    get_table_info_as_create_table,
)

logger = logging.getLogger(__name__)


class SQLResultChain(BaseDocugamiChain[ExplainedSQLResult]):
    db: SQLDatabase
    """The underlying SQL database that is queried by this chain."""

    sql_fixup_chain: Optional[SQLFixupChain] = None
    """A chain used to fix SQL generated by this chain in case of issues."""

    _example_row_selector: Optional[MaxMarginalRelevanceExampleSelector] = None

    def optimize(self) -> None:
        """
        Optimizes the database for few shot rows selection. This is optional
        but recommended. If you don't run optimize, then the first N rows are
        returned in table info without considering similarity.
        """
        if self.embeddings:
            self._example_row_selector = create_example_selector(
                self.db, self.embeddings, self.examples_vectorstore_cls
            )

    def runnable(self) -> Runnable:
        """
        Custom runnable for this chain.
        """

        def table_info_func(inputs: dict) -> str:
            """
            Return the table info for the database connection for this chain.
            """
            question = inputs.get("question")
            return get_table_info_as_create_table(
                self.db,
                question=question,
                example_selector=self._example_row_selector,
            )

        def run_sql_query(
            inputs: dict, config: Optional[RunnableConfig]
        ) -> ExplainedSQLResult:
            """
            Runs the given SQL query against the database connection for this chain, and returns the result.
            """

            question = inputs.get("question")
            sql_query = inputs.get("sql_query")
            table_info = table_info_func({"question": question})

            if not question or not sql_query or not table_info:
                raise Exception("Inputs required: question, sql_query, table_info")

            try:
                sql_query = check_and_format_query(self.db, sql_query)

                # Run
                return {
                    "question": question,
                    "sql_query": sql_query,
                    "sql_result": str(self.db.run(sql_query)).strip(),
                }

            except Exception as exc:
                # If any exception with Raw SQL, try to fix up the SQL
                # giving the LLM context on the exception to aid fixup
                fixed_sql_response = self.sql_fixup_chain.run(
                    table_info=table_info,
                    sql_query=sql_query,
                    exception=str(exc),
                    config=config,  # Pass the config down to link traces in langsmith
                )

                # Run Fixed-up SQL
                fixed_sql = fixed_sql_response.value
                fixed_sql = check_and_format_query(self.db, fixed_sql)

                return {
                    "question": question,
                    "sql_query": fixed_sql,
                    "sql_result": str(self.db.run(fixed_sql)).strip(),
                }

        return {
            "question": itemgetter("question"),
            "sql_query": {
                "question": itemgetter("question"),
                "table_info": RunnableLambda(table_info_func),
            }
            | super().runnable()
            | SQLFindingOutputParser(),
        } | RunnableLambda(run_sql_query)

    def params(self) -> RunnableParameters:
        return RunnableParameters(
            inputs=[
                RunnableSingleParameter(
                    "question",
                    "QUESTION",
                    "Question asked by the user.",
                ),
                RunnableSingleParameter(
                    "table_info",
                    "TABLE DESCRIPTION",
                    "Description of the table to be queried via SQL.",
                ),
            ],
            output=RunnableSingleParameter(
                "sql_query",
                "SQL QUERY",
                "SQL Query that should be run against the table to answer the question, considering the rules and examples provided. Do NOT generate a direct non-SQL answer, even if you know it."
                + " Always produce only SQL as output.",
            ),
            task_description="only generates SQL as output. Given an input SQL table description and a question, you generate an equivalent syntactically correct SQLite query against the given table",
            additional_instructions=[
                "- Only generate SQL as output, don't generate any other language e.g. do not try to directly answer the question asked.",
                '- If the question is ambiguous or you don\'t know how to answer it in the form of a SQL QUERY, just dump the first row of the table i.e. SELECT * FROM "Table Name" LIMIT 1.',
                "- Unless the user specifies in the question a specific number of examples to obtain, query for at most 5 results using the LIMIT clause as per SQLite.",
                "- If needed, order the results to return the most informative data in the database.",
                "- Never query for all columns from a table. You must query only the columns that are needed to answer the question.",
                '- Wrap each column name in the query in double quotes (") to denote them as delimited identifiers.',
                "- Pay attention to use only the column names you can see in the given tables. Be careful to not query for columns that do not exist.",
                "- Pay attention to use the date('now') function to get the current date, if the question involves \"today\".",
                """- When matching strings in WHERE clauses, always use LIKE with LOWER rather than exact string match with "=" since users may not fully specify complete input with the right """
                + """casing, for example generate SELECT * from "athletes" WHERE LOWER("last name") LIKE '%jones%' instead of SELECT * from "athletes" WHERE "last name" = 'Jones'""",
                "- Never provide any additional explanation or discussion, only output the SQLite query requested, which answers the question against the given table description.",
                "- If example rows are given, pay special attention to them to improve your query e.g. to account for abbreviations or formatting of values.",
            ],
            stop_sequences=["\n", ";", "<|eot_id|>"],
            additional_runnables=[TextCleaningOutputParser(), SQLFindingOutputParser()],
        )

    def run(  # type: ignore[override]
        self,
        question: str,
        config: Optional[RunnableConfig] = None,
    ) -> TracedResponse[ExplainedSQLResult]:
        if not question:
            raise Exception("Input required: question")

        return super().run(
            question=question,
            config=config,
        )

    async def run_stream(  # type: ignore[override]
        self,
        question: str,
        config: Optional[RunnableConfig] = None,
    ) -> AsyncIterator[TracedResponse[ExplainedSQLResult]]:
        if not question:
            raise Exception("Input required: question")

        async for item in super().run_stream(
            question=question,
            config=config,
        ):
            yield item

    def run_batch(  # type: ignore[override]
        self,
        inputs: list[str],
        config: Optional[RunnableConfig] = None,
    ) -> list[ExplainedSQLResult]:
        return super().run_batch(
            inputs=[{"question": i} for i in inputs],
            config=config,
        )
