# pylint: disable=no-member
import time
from pathlib import PosixPath

import pandas as pd
import pytest
import sqlalchemy

from kedro.extras.datasets.pandas import SQLQueryDataSet, SQLTableDataSet
from kedro.io import DataSetError

TABLE_NAME = "table_a"
CONNECTION = "sqlite:///kedro.db"
SQL_QUERY = "SELECT * FROM table_a"
FAKE_CONN_STR = "some_sql://scott:tiger@localhost/foo"
ERROR_PREFIX = (
    r"A module\/driver is missing when connecting to your SQL server\.(.|\n)*"
)


@pytest.fixture
def dummy_dataframe():
    return pd.DataFrame({"col1": [1, 2], "col2": [4, 5], "col3": [5, 6]})


@pytest.fixture
def sql_file(tmp_path: PosixPath):
    file = tmp_path / "test.sql"
    file.write_text(SQL_QUERY)
    return file.as_posix()


@pytest.fixture(params=[{}])
def table_data_set(request):
    kwargs = dict(table_name=TABLE_NAME, credentials=dict(con=CONNECTION))
    kwargs.update(request.param)
    return SQLTableDataSet(**kwargs)


@pytest.fixture(params=[{}])
def query_data_set(request):
    kwargs = dict(sql=SQL_QUERY, credentials=dict(con=CONNECTION))
    kwargs.update(request.param)
    return SQLQueryDataSet(**kwargs)


@pytest.fixture(params=[{}])
def query_file_data_set(request, sql_file):
    kwargs = dict(filepath=sql_file, credentials=dict(con=CONNECTION))
    kwargs.update(request.param)
    return SQLQueryDataSet(**kwargs)


class TestSQLTableDataSetLoad:
    def test_empty_table_name(self):
        """Check the error when instantiating with an empty table"""
        pattern = r"`table\_name` argument cannot be empty\."
        with pytest.raises(DataSetError, match=pattern):
            SQLTableDataSet(table_name="", credentials=dict(con=CONNECTION))

    def test_empty_connection(self):
        """Check the error when instantiating with an empty
        connection string"""
        pattern = (
            r"`con` argument cannot be empty\. "
            r"Please provide a SQLAlchemy connection string\."
        )
        with pytest.raises(DataSetError, match=pattern):
            SQLTableDataSet(table_name=TABLE_NAME, credentials=dict(con=""))

    def test_load_sql_params(self, mocker, table_data_set):
        """Test `load` method invocation"""
        mocker.patch("pandas.read_sql_table")
        table_data_set.load()
        pd.read_sql_table.assert_called_once_with(
            table_name=TABLE_NAME, con=table_data_set.engine
        )

    def test_load_driver_missing(self, mocker, table_data_set):
        """Check the error when the sql driver is missing"""
        mocker.patch(
            "pandas.read_sql_table",
            side_effect=ImportError("No module named 'mysqldb'"),
        )
        with pytest.raises(DataSetError, match=ERROR_PREFIX + "mysqlclient"):
            table_data_set.load()
        pd.read_sql_table.assert_called_once_with(
            table_name=TABLE_NAME, con=table_data_set.engine
        )

    def test_invalid_module(self, mocker, table_data_set):
        """Test that if an invalid module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("Invalid module some_module")
        mocker.patch("pandas.read_sql_table", side_effect=_err)
        pattern = ERROR_PREFIX + r"Invalid module some\_module"
        with pytest.raises(DataSetError, match=pattern):
            table_data_set.load()
        pd.read_sql_table.assert_called_once_with(
            table_name=TABLE_NAME, con=table_data_set.engine
        )

    def test_load_unknown_module(self, mocker, table_data_set):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        mocker.patch(
            "pandas.read_sql_table",
            side_effect=ImportError("No module named 'unknown_module'"),
        )
        pattern = ERROR_PREFIX + r"No module named \'unknown\_module\'"
        with pytest.raises(DataSetError, match=pattern):
            table_data_set.load()

    @pytest.mark.parametrize(
        "table_data_set", [{"credentials": dict(con=FAKE_CONN_STR)}], indirect=True
    )
    def test_load_unknown_sql(self, table_data_set):
        """Check the error when unknown sql dialect is provided"""
        pattern = r"The SQL dialect in your connection is not supported by SQLAlchemy"
        with pytest.raises(DataSetError, match=pattern):
            table_data_set.load()


class TestSQLTableDataSetSave:
    _unknown_conn = "mysql+unknown_module://scott:tiger@localhost/foo"

    def test_save_default_index(self, mocker, table_data_set, dummy_dataframe):
        """Test `save` method invocation"""
        mocker.patch.object(dummy_dataframe, "to_sql")
        table_data_set.save(dummy_dataframe)
        dummy_dataframe.to_sql.assert_called_once_with(
            name=TABLE_NAME, con=table_data_set.engine, index=False
        )

    @pytest.mark.parametrize(
        "table_data_set", [{"save_args": dict(index=True)}], indirect=True
    )
    def test_save_overwrite_index(self, mocker, table_data_set, dummy_dataframe):
        """Test writing DataFrame index as a column"""
        mocker.patch.object(dummy_dataframe, "to_sql")
        table_data_set.save(dummy_dataframe)
        dummy_dataframe.to_sql.assert_called_once_with(
            name=TABLE_NAME, con=table_data_set.engine, index=True
        )

    def test_save_driver_missing(self, mocker, table_data_set, dummy_dataframe):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("No module named 'mysqldb'")
        mocker.patch.object(dummy_dataframe, "to_sql", side_effect=_err)
        with pytest.raises(DataSetError, match=ERROR_PREFIX + "mysqlclient"):
            table_data_set.save(dummy_dataframe)

    @pytest.mark.parametrize(
        "table_data_set", [{"credentials": dict(con=FAKE_CONN_STR)}], indirect=True
    )
    def test_save_unknown_sql(self, table_data_set, dummy_dataframe):
        """Check the error when unknown sql dialect is provided"""
        pattern = r"The SQL dialect in your connection is not supported by SQLAlchemy"
        with pytest.raises(DataSetError, match=pattern):
            table_data_set.save(dummy_dataframe)

    @pytest.mark.parametrize(
        "table_data_set", [{"credentials": dict(con=_unknown_conn)}], indirect=True
    )
    def test_save_unknown_module(self, mocker, table_data_set, dummy_dataframe):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("No module named 'unknown_module'")
        mocker.patch.object(dummy_dataframe, "to_sql", side_effect=_err)
        pattern = r"No module named \'unknown_module\'"
        with pytest.raises(DataSetError, match=pattern):
            table_data_set.save(dummy_dataframe)

    @pytest.mark.parametrize(
        "table_data_set", [{"save_args": dict(name="TABLE_B")}], indirect=True
    )
    def test_save_ignore_table_name_override(
        self, mocker, table_data_set, dummy_dataframe
    ):
        """Test that putting the table name is `save_args` does not have any
        effect"""
        mocker.patch.object(dummy_dataframe, "to_sql")
        table_data_set.save(dummy_dataframe)
        dummy_dataframe.to_sql.assert_called_once_with(
            name=TABLE_NAME, con=table_data_set.engine, index=False
        )


class TestSQLTableDataSet:
    @staticmethod
    def _assert_sqlalchemy_called_once(*args):
        _callable = sqlalchemy.engine.Engine.table_names
        if args:
            _callable.assert_called_once_with(*args)
        else:
            assert _callable.call_count == 1

    def test_str_representation_table(self, table_data_set):
        """Test the data set instance string representation"""
        str_repr = str(table_data_set)
        assert (
            "SQLTableDataSet(load_args={}, save_args={'index': False}, "
            f"table_name={TABLE_NAME})" in str_repr
        )
        assert CONNECTION not in str(str_repr)

    def test_table_exists(self, mocker, table_data_set):
        """Test `exists` method invocation"""
        mocker.patch("sqlalchemy.engine.Engine.table_names")
        assert not table_data_set.exists()
        self._assert_sqlalchemy_called_once()

    @pytest.mark.parametrize(
        "table_data_set", [{"load_args": dict(schema="ingested")}], indirect=True
    )
    def test_table_exists_schema(self, mocker, table_data_set):
        """Test `exists` method invocation with DB schema provided"""
        mocker.patch("sqlalchemy.engine.Engine.table_names")
        assert not table_data_set.exists()
        self._assert_sqlalchemy_called_once("ingested")

    def test_table_exists_mocked(self, mocker, table_data_set):
        """Test `exists` method invocation with mocked list of tables"""
        mocker.patch("sqlalchemy.engine.Engine.table_names", return_value=[TABLE_NAME])
        assert table_data_set.exists()
        self._assert_sqlalchemy_called_once()


class TestSQLTableDataSetSingleConnection:
    def test_single_connection_performance(self, dummy_dataframe):
        kwargs = dict(
            save_args=dict(if_exists="append"),
            table_name=TABLE_NAME,
            credentials=dict(con=CONNECTION),
        )
        datasets = [SQLTableDataSet(**kwargs) for _ in range(10)]

        for d in datasets:
            d.save(dummy_dataframe)

        start = time.time()
        for d in datasets:
            d.load()
        end = time.time()

        delta = end - start
        print(delta)
        datasets[0].engine.dispose()

    def test_single_connection(self, dummy_dataframe, mocker):
        """Test to make sure multiple instances use the same connection object."""
        dummy_to_sql = mocker.patch.object(dummy_dataframe, "to_sql")
        kwargs = dict(table_name=TABLE_NAME, credentials=dict(con=CONNECTION))

        first = SQLTableDataSet(**kwargs)
        unique_connection = first.engine
        datasets = [SQLTableDataSet(**kwargs) for _ in range(10)]

        for ds in datasets:
            ds.save(dummy_dataframe)
            assert ds.engine is unique_connection

        expected_call = mocker.call(name=TABLE_NAME, con=unique_connection, index=False)
        dummy_to_sql.assert_has_calls([expected_call] * 10)

        # for d in datasets:
        #     d.load()


class TestSQLQueryDataSet:
    def test_empty_query_error(self):
        """Check the error when instantiating with empty query or file"""
        pattern = (
            r"`sql` and `filepath` arguments cannot both be empty\."
            r"Please provide a sql query or path to a sql query file\."
        )
        with pytest.raises(DataSetError, match=pattern):
            SQLQueryDataSet(sql="", filepath="", credentials=dict(con=CONNECTION))

    def test_empty_con_error(self):
        """Check the error when instantiating with empty connection string"""
        pattern = (
            r"`con` argument cannot be empty\. Please provide "
            r"a SQLAlchemy connection string"
        )
        with pytest.raises(DataSetError, match=pattern):
            SQLQueryDataSet(sql=SQL_QUERY, credentials=dict(con=""))

    def test_load(self, mocker, query_data_set):
        """Test `load` method invocation"""
        mocker.patch("pandas.read_sql_query")
        query_data_set.load()
        pd.read_sql_query.assert_called_once_with(
            sql=SQL_QUERY, con=query_data_set.engine
        )

    def test_load_query_file(self, mocker, query_file_data_set):
        """Test `load` method with a query file"""
        mocker.patch("pandas.read_sql_query")
        query_file_data_set.load()
        pd.read_sql_query.assert_called_once_with(
            sql=SQL_QUERY, con=query_file_data_set.engine
        )

    def test_load_driver_missing(self, mocker, query_data_set):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("No module named 'mysqldb'")
        mocker.patch("pandas.read_sql_query", side_effect=_err)
        with pytest.raises(DataSetError, match=ERROR_PREFIX + "mysqlclient"):
            query_data_set.load()

    def test_invalid_module(self, mocker, query_data_set):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("Invalid module some_module")
        mocker.patch("pandas.read_sql_query", side_effect=_err)
        pattern = ERROR_PREFIX + r"Invalid module some\_module"
        with pytest.raises(DataSetError, match=pattern):
            query_data_set.load()

    def test_load_unknown_module(self, mocker, query_data_set):
        """Test that if an unknown module/driver is encountered by SQLAlchemy
        then the error should contain the original error message"""
        _err = ImportError("No module named 'unknown_module'")
        mocker.patch("pandas.read_sql_query", side_effect=_err)
        pattern = ERROR_PREFIX + r"No module named \'unknown\_module\'"
        with pytest.raises(DataSetError, match=pattern):
            query_data_set.load()

    @pytest.mark.parametrize(
        "query_data_set", [{"credentials": dict(con=FAKE_CONN_STR)}], indirect=True
    )
    def test_load_unknown_sql(self, query_data_set):
        """Check the error when unknown SQL dialect is provided
        in the connection string"""
        pattern = r"The SQL dialect in your connection is not supported by SQLAlchemy"
        with pytest.raises(DataSetError, match=pattern):
            query_data_set.load()

    def test_save_error(self, query_data_set, dummy_dataframe):
        """Check the error when trying to save to the data set"""
        pattern = r"`save` is not supported on SQLQueryDataSet"
        with pytest.raises(DataSetError, match=pattern):
            query_data_set.save(dummy_dataframe)

    def test_str_representation_sql(self, query_data_set, sql_file):
        """Test the data set instance string representation"""
        str_repr = str(query_data_set)
        assert (
            f"SQLQueryDataSet(filepath=None, load_args={{}}, sql={SQL_QUERY})"
            in str_repr
        )
        assert CONNECTION not in str_repr
        assert sql_file not in str_repr

    def test_str_representation_filepath(self, query_file_data_set, sql_file):
        """Test the data set instance string representation with filepath arg."""
        str_repr = str(query_file_data_set)
        assert (
            f"SQLQueryDataSet(filepath={str(sql_file)}, load_args={{}}, sql=None)"
            in str_repr
        )
        assert CONNECTION not in str_repr
        assert SQL_QUERY not in str_repr

    def test_sql_and_filepath_args(self, sql_file):
        """Test that an error is raised when both `sql` and `filepath` args are given."""
        pattern = (
            r"`sql` and `filepath` arguments cannot both be provided."
            r"Please only provide one."
        )
        with pytest.raises(DataSetError, match=pattern):
            SQLQueryDataSet(sql=SQL_QUERY, filepath=sql_file)
