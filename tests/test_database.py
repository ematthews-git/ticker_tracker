import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone

from storage.database_manager import (
    insert_mention_counts,
    fetch_ticker_mentions,
    fetch_popular_tickers,
    fetch_growth_tickers,
)
from models import MentionDataPoint


class TestDatabase(unittest.TestCase):
    """Base class with shared fixtures"""

    def setUp(self):
        self.test_timestamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.test_timestamp2 = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        self.sample_data_point = MentionDataPoint(
            ticker="AAPL",
            subreddit="pennystocks",
            timestamp=self.test_timestamp,
            mention_count=10,
            unique_users=5,
            total_score=100,
            total_comments=20,
            avg_sentiment=0.5,
        )

    def _make_mock_pool(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        return mock_pool, mock_conn, mock_cursor


class TestInsertMentionCounts(TestDatabase):
    @patch("storage.database_manager.execute_batch")
    def test_inserts_single_mention(self, mock_execute_batch):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        insert_mention_counts(mock_pool, [self.sample_data_point])

        mock_pool.getconn.assert_called_once()
        mock_execute_batch.assert_called_once()
        call_args = mock_execute_batch.call_args

        self.assertEqual(call_args[0][0], mock_cursor)
        self.assertIn("INSERT INTO mentions", call_args[0][1])
        self.assertIn("ON CONFLICT", call_args[0][1])

        data = call_args[0][2]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0][0], "AAPL")
        self.assertEqual(data[0][1], "pennystocks")
        self.assertEqual(data[0][2], self.test_timestamp)
        self.assertEqual(data[0][3], 10)
        self.assertEqual(data[0][4], 5)
        self.assertEqual(data[0][5], 100)
        self.assertEqual(data[0][6], 20)
        self.assertEqual(data[0][7], 0.5)

        mock_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    @patch("storage.database_manager.execute_batch")
    def test_inserts_multiple_mentions(self, mock_execute_batch):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        data_points = [
            self.sample_data_point,
            MentionDataPoint(
                ticker="TSLA",
                subreddit="wallstreetbets",
                timestamp=self.test_timestamp2,
                mention_count=20,
                unique_users=10,
                total_score=200,
                total_comments=30,
                avg_sentiment=0.7,
            ),
        ]

        insert_mention_counts(mock_pool, data_points)

        call_args = mock_execute_batch.call_args
        data = call_args[0][2]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0][0], "AAPL")
        self.assertEqual(data[1][0], "TSLA")

    def test_handles_empty_list(self):
        mock_pool = MagicMock()
        insert_mention_counts(mock_pool, [])
        mock_pool.getconn.assert_not_called()

    @patch("storage.database_manager.execute_batch")
    def test_uppercases_ticker(self, mock_execute_batch):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()

        data_point = MentionDataPoint(
            ticker="aapl",
            subreddit="pennystocks",
            timestamp=self.test_timestamp,
            mention_count=10,
            unique_users=5,
            total_score=100,
            total_comments=20,
            avg_sentiment=0.5,
        )

        insert_mention_counts(mock_pool, [data_point])

        call_args = mock_execute_batch.call_args
        data = call_args[0][2]
        self.assertEqual(data[0][0], "AAPL")

    @patch("storage.database_manager.execute_batch")
    @patch("storage.database_manager.logger")
    def test_handles_database_error(self, mock_logger, mock_execute_batch):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_execute_batch.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            insert_mention_counts(mock_pool, [self.sample_data_point])

        mock_conn.rollback.assert_called_once()
        mock_logger.error.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestFetchTickerMentions(TestDatabase):
    def test_fetches_mentions_for_ticker(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            ("AAPL", "pennystocks", self.test_timestamp, 10, 5, 100, 20, 0.5),
            ("AAPL", "wallstreetbets", self.test_timestamp2, 15, 8, 150, 25, 0.6),
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_ticker_mentions(mock_pool, "AAPL", start_date, end_date)

        mock_pool.getconn.assert_called_once()
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        self.assertIn("SELECT", call_args[0][0])
        self.assertIn("WHERE ticker = %s", call_args[0][0])
        self.assertIn("BETWEEN", call_args[0][0])

        params = call_args[0][1]
        self.assertEqual(params[0], "AAPL")
        self.assertEqual(params[1], start_date)
        self.assertEqual(params[2], end_date)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].ticker, "AAPL")
        self.assertEqual(result[0].subreddit, "pennystocks")
        self.assertEqual(result[0].mention_count, 10)
        self.assertEqual(result[1].subreddit, "wallstreetbets")
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_uppercases_ticker_in_query(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_ticker_mentions(
            mock_pool,
            "aapl",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[0], "AAPL")

    def test_returns_empty_list_when_no_results(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        result = fetch_ticker_mentions(
            mock_pool,
            "AAPL",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, list)

    def test_converts_data_types_correctly(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            ("AAPL", "pennystocks", self.test_timestamp, "10", "5", "100", "20", "0.5")
        ]

        result = fetch_ticker_mentions(
            mock_pool,
            "AAPL",
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(result[0].mention_count, 10)
        self.assertIsInstance(result[0].mention_count, int)
        self.assertIsInstance(result[0].avg_sentiment, float)

    @patch("storage.database_manager.logger")
    def test_handles_database_error(self, mock_logger):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.execute.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            fetch_ticker_mentions(
                mock_pool,
                "AAPL",
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

        mock_logger.error.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)


class TestFetchPopularTickers(TestDatabase):
    def test_fetches_popular_tickers(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            ("TSLA", "pennystocks", self.test_timestamp, 50, 20, 500, 100, 0.8),
            ("TSLA", "wallstreetbets", self.test_timestamp2, 30, 15, 300, 50, 0.7),
            ("AAPL", "pennystocks", self.test_timestamp, 25, 10, 250, 40, 0.6),
        ]

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 3, tzinfo=timezone.utc)

        result = fetch_popular_tickers(mock_pool, start_date, end_date, amount=2)

        mock_pool.getconn.assert_called_once()
        call_args = mock_cursor.execute.call_args
        self.assertIn("WITH top_tickers AS", call_args[0][0])
        self.assertIn("SUM(mention_count)", call_args[0][0])
        self.assertIn("LIMIT %s", call_args[0][0])

        params = call_args[0][1]
        self.assertEqual(params[2], 2)

        self.assertIsInstance(result, dict)
        self.assertIn("TSLA", result)
        self.assertIn("AAPL", result)
        self.assertEqual(len(result["TSLA"]), 2)
        self.assertEqual(len(result["AAPL"]), 1)
        mock_pool.putconn.assert_called_once_with(mock_conn)

    def test_uses_default_amount(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_popular_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[2], 10)

    def test_returns_empty_dict_when_no_results(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        result = fetch_popular_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result), 0)
        self.assertIsInstance(result, dict)

    def test_groups_mentions_by_ticker(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            ("AAPL", "pennystocks", self.test_timestamp, 10, 5, 100, 20, 0.5),
            ("AAPL", "wallstreetbets", self.test_timestamp, 15, 8, 150, 25, 0.6),
            ("AAPL", "pennystocks", self.test_timestamp2, 20, 10, 200, 30, 0.7),
        ]

        result = fetch_popular_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
            amount=1,
        )

        self.assertEqual(len(result), 1)
        self.assertIn("AAPL", result)
        self.assertEqual(len(result["AAPL"]), 3)

    @patch("storage.database_manager.logger")
    def test_handles_database_error(self, mock_logger):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.execute.side_effect = Exception("Database error")

        with self.assertRaises(Exception):
            fetch_popular_tickers(
                mock_pool,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

        mock_logger.error.assert_called_once()
        mock_cursor.close.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)

    @patch("storage.database_manager.logger")
    def test_logs_debug_info(self, mock_logger):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_popular_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        mock_logger.debug.assert_called_once()
        self.assertIn("rows", mock_logger.debug.call_args[0][0].lower())


class TestFetchGrowthTickers(TestDatabase):
    """Test suite for fetch_growth_tickers function"""

    def _make_growth_row(
        self,
        ticker,
        subreddit,
        timestamp,
        count,
        growth_rate,
        unique_users=5,
        total_score=100,
        total_comments=10,
        avg_sentiment=0.0,
    ):
        return (
            ticker,
            subreddit,
            timestamp,
            count,
            unique_users,
            total_score,
            total_comments,
            avg_sentiment,
            growth_rate,
        )

    def test_returns_dict_with_growth_rate_and_data_points(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            self._make_growth_row("AAPL", "pennystocks", self.test_timestamp, 30, 50.0),
            self._make_growth_row(
                "AAPL", "wallstreetbets", self.test_timestamp2, 20, 50.0
            ),
            self._make_growth_row("TSLA", "pennystocks", self.test_timestamp, 15, 25.0),
        ]

        result = fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertIsInstance(result, dict)
        self.assertIn("AAPL", result)
        self.assertIn("TSLA", result)
        growth_rate, data_points = result["AAPL"]
        self.assertIsInstance(growth_rate, float)
        self.assertEqual(growth_rate, 50.0)
        self.assertIsInstance(data_points, list)
        self.assertEqual(len(data_points), 2)
        self.assertEqual(data_points[0].ticker, "AAPL")
        self.assertEqual(result["TSLA"][0], 25.0)
        self.assertEqual(len(result["TSLA"][1]), 1)

    def test_new_ticker_growth_rate_999999(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            self._make_growth_row(
                "GME", "pennystocks", self.test_timestamp, 10, 999999
            ),
        ]

        result = fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertIn("GME", result)
        self.assertEqual(result["GME"][0], 999999.0)

    def test_empty_db_returns_empty_dict(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        result = fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(result, {})
        self.assertIsInstance(result, dict)

    def test_amount_passed_as_4th_sql_param(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
            amount=5,
        )

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[3], 5)

    def test_uses_default_amount_10(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[3], 10)

    def test_midpoint_calculated_correctly(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(2025, 1, 11, tzinfo=timezone.utc)
        expected_midpoint = datetime(2025, 1, 6, tzinfo=timezone.utc)

        fetch_growth_tickers(mock_pool, start_date, end_date)

        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params[0], expected_midpoint)

    def test_sql_contains_required_cte_names(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = []

        fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("WITH period_mentions AS", sql)
        self.assertIn("growth_calc", sql)
        self.assertIn("ticker_growth", sql)
        self.assertIn("999999", sql)
        self.assertIn("recent_mentions > 0", sql)

    def test_multiple_data_points_per_ticker(self):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.fetchall.return_value = [
            self._make_growth_row("AAPL", "pennystocks", self.test_timestamp, 10, 75.0),
            self._make_growth_row(
                "AAPL", "wallstreetbets", self.test_timestamp, 15, 75.0
            ),
            self._make_growth_row(
                "AAPL", "pennystocks", self.test_timestamp2, 20, 75.0
            ),
        ]

        result = fetch_growth_tickers(
            mock_pool,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 3, tzinfo=timezone.utc),
        )

        self.assertEqual(result["AAPL"][0], 75.0)
        self.assertEqual(len(result["AAPL"][1]), 3)

    @patch("storage.database_manager.logger")
    def test_error_handling_logs_and_reraises(self, mock_logger):
        mock_pool, mock_conn, mock_cursor = self._make_mock_pool()
        mock_cursor.execute.side_effect = Exception("DB timeout")

        with self.assertRaises(Exception):
            fetch_growth_tickers(
                mock_pool,
                datetime(2025, 1, 1, tzinfo=timezone.utc),
                datetime(2025, 1, 3, tzinfo=timezone.utc),
            )

        mock_logger.error.assert_called_once()
        mock_pool.putconn.assert_called_once_with(mock_conn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
