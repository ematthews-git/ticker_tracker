import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta, timezone

import pandas as pd
import numpy as np

from market.price_fetcher import PriceCollector


def _make_price_df(rows=1, include_nan=False):
    """Build a simple single-ticker OHLCV DataFrame as yfinance returns for a single ticker."""
    idx = pd.date_range("2025-01-15", periods=rows, freq="h", tz="UTC")
    close_vals = [153.0] * rows
    if include_nan:
        close_vals[0] = float("nan")
    return pd.DataFrame(
        {
            "Open": [150.0] * rows,
            "High": [155.0] * rows,
            "Low": [148.0] * rows,
            "Close": close_vals,
            "Volume": [1_000_000] * rows,
        },
        index=idx,
    )


def _make_multi_ticker_df(tickers):
    """Build a MultiIndex-column DataFrame as yfinance returns for multiple tickers.

    yfinance multi-ticker download: level 0 = ticker, level 1 = field, so
    `data[ticker]` selects by level 0 and returns a single-level DataFrame.
    """
    idx = pd.date_range("2025-01-15", periods=2, freq="h", tz="UTC")
    fields = ["Open", "High", "Low", "Close", "Volume"]
    col_index = pd.MultiIndex.from_product([tickers, fields], names=["Ticker", "Price"])
    data = {}
    for ticker in tickers:
        for field in fields:
            val = 1_000_000 if field == "Volume" else 150.0
            data[(ticker, field)] = [val, val]
    return pd.DataFrame(data, index=idx, columns=col_index)


class TestPriceCollectorBase(unittest.TestCase):
    def setUp(self):
        self.mock_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_pool.getconn.return_value = self.mock_conn
        self.mock_conn.cursor.return_value = self.mock_cursor

        self.collector = PriceCollector(self.mock_pool)
        self.test_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# collect_and_store_prices
# ---------------------------------------------------------------------------


class TestCollectAndStorePrices(TestPriceCollectorBase):
    @patch("market.price_fetcher.helper")
    def test_no_active_tickers_returns_early(self, mock_helper):
        mock_helper.get_active_tickers.return_value = []

        with (
            patch.object(self.collector, "fetch_and_store_prices") as mock_fas,
            self.assertLogs("market.price_fetcher", level="WARNING"),
        ):
            self.collector.collect_and_store_prices(self.test_time)

        mock_fas.assert_not_called()

    @patch("market.price_fetcher.VALID", {"AAPL", "TSLA"})
    @patch("market.price_fetcher.helper")
    def test_no_valid_tickers_after_filtering_returns_early(self, mock_helper):
        mock_helper.get_active_tickers.return_value = ["FAKEXYZ"]

        with (
            patch.object(self.collector, "fetch_and_store_prices") as mock_fas,
            self.assertLogs("market.price_fetcher", level="WARNING"),
        ):
            self.collector.collect_and_store_prices(self.test_time)

        mock_fas.assert_not_called()

    @patch("market.price_fetcher.VALID", {"AAPL", "TSLA"})
    @patch("market.price_fetcher.helper")
    def test_normal_flow_calls_fetch_and_store(self, mock_helper):
        mock_helper.get_active_tickers.return_value = ["AAPL", "TSLA"]

        with patch.object(self.collector, "fetch_and_store_prices") as mock_fas:
            self.collector.collect_and_store_prices(self.test_time)

        mock_fas.assert_called_once_with(["AAPL", "TSLA"], days_back=5)

    @patch("market.price_fetcher.VALID", {"AAPL"})
    @patch("market.price_fetcher.helper")
    def test_uses_24h_window_and_min_mentions_2(self, mock_helper):
        mock_helper.get_active_tickers.return_value = []

        with self.assertLogs("market.price_fetcher", level="WARNING"):
            self.collector.collect_and_store_prices(self.test_time)

        call_args = mock_helper.get_active_tickers.call_args
        _, kwargs = call_args
        # First positional args: pool, start_time, current_time, min_mentions
        args = call_args[0]
        start_time = args[1]
        current_time = args[2]
        min_mentions = kwargs.get("min_mentions", args[3] if len(args) > 3 else None)

        self.assertEqual(current_time, self.test_time)
        self.assertEqual(start_time, self.test_time - timedelta(hours=24))
        self.assertEqual(min_mentions, 2)


# ---------------------------------------------------------------------------
# _fetch_hourly_prices
# ---------------------------------------------------------------------------


class TestFetchHourlyPrices(TestPriceCollectorBase):
    def setUp(self):
        super().setUp()
        patcher = patch("market.price_fetcher.record_failures")
        self.mock_record_failures = patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_list_returns_empty_dict(self):
        with patch("market.price_fetcher.yf") as mock_yf:
            result = self.collector._fetch_hourly_prices([])

        self.assertEqual(result, {})
        mock_yf.download.assert_not_called()

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_single_ticker_stored_directly(self, mock_yf, mock_time):
        df = _make_price_df()
        mock_yf.download.return_value = df

        result = self.collector._fetch_hourly_prices(["AAPL"])

        self.assertIn("AAPL", result)
        self.assertTrue(result["AAPL"].equals(df))

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_multi_ticker_indexed_by_ticker(self, mock_yf, mock_time):
        multi_df = _make_multi_ticker_df(["AAPL", "TSLA"])
        mock_yf.download.return_value = multi_df

        result = self.collector._fetch_hourly_prices(["AAPL", "TSLA"])

        self.assertIn("AAPL", result)
        self.assertIn("TSLA", result)

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_chunks_into_groups_of_20(self, mock_yf, mock_time):
        # Return empty df so no ticker is added to results, but we can count calls
        mock_yf.download.return_value = pd.DataFrame()
        tickers = [f"T{i:02d}" for i in range(25)]

        self.collector._fetch_hourly_prices(tickers)

        self.assertEqual(mock_yf.download.call_count, 2)
        first_call_tickers = mock_yf.download.call_args_list[0][0][0].split()
        second_call_tickers = mock_yf.download.call_args_list[1][0][0].split()
        self.assertEqual(len(first_call_tickers), 20)
        self.assertEqual(len(second_call_tickers), 5)

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_failed_chunk_excluded_from_results(self, mock_yf, mock_time):
        mock_yf.download.side_effect = Exception("API timeout")

        with self.assertLogs("market.price_fetcher", level="WARNING"):
            result = self.collector._fetch_hourly_prices(["AAPL"])

        self.assertEqual(result, {})

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_period_is_1mo_for_more_than_5_days(self, mock_yf, mock_time):
        mock_yf.download.return_value = pd.DataFrame()

        self.collector._fetch_hourly_prices(["AAPL"], days_back=10)
        _, kwargs = mock_yf.download.call_args
        self.assertEqual(kwargs["period"], "1mo")

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_period_is_Nd_for_5_days_or_fewer(self, mock_yf, mock_time):
        mock_yf.download.return_value = pd.DataFrame()

        self.collector._fetch_hourly_prices(["AAPL"], days_back=5)
        _, kwargs = mock_yf.download.call_args
        self.assertEqual(kwargs["period"], "5d")

    @patch("market.price_fetcher.time")
    @patch("market.price_fetcher.yf")
    def test_sleep_called_between_chunks(self, mock_yf, mock_time):
        mock_yf.download.return_value = pd.DataFrame()
        tickers = [f"T{i:02d}" for i in range(25)]

        self.collector._fetch_hourly_prices(tickers)

        # sleep called once per chunk (2 chunks)
        self.assertEqual(mock_time.sleep.call_count, 2)
        mock_time.sleep.assert_called_with(0.5)


# ---------------------------------------------------------------------------
# save_prices_to_db
# ---------------------------------------------------------------------------


class TestSavePricesToDb(TestPriceCollectorBase):
    @patch("market.price_fetcher.execute_batch")
    def test_empty_dataframe_returns_early(self, mock_execute_batch):
        self.collector.save_prices_to_db("AAPL", pd.DataFrame())

        self.mock_pool.getconn.assert_not_called()
        mock_execute_batch.assert_not_called()

    @patch("market.price_fetcher.execute_batch")
    def test_nan_rows_skipped(self, mock_execute_batch):
        df = _make_price_df(rows=2, include_nan=True)  # row 0 has NaN Close

        self.collector.save_prices_to_db("AAPL", df)

        data = mock_execute_batch.call_args[0][2]
        self.assertEqual(len(data), 1)

    @patch("market.price_fetcher.execute_batch")
    def test_upsert_sql_structure(self, mock_execute_batch):
        df = _make_price_df()

        self.collector.save_prices_to_db("AAPL", df)

        sql = mock_execute_batch.call_args[0][1]
        self.assertIn("INSERT INTO stock_prices", sql)
        self.assertIn("ON CONFLICT (ticker, timestamp)", sql)
        self.assertIn("DO UPDATE SET", sql)

    @patch("market.price_fetcher.execute_batch")
    def test_ticker_uppercased(self, mock_execute_batch):
        df = _make_price_df()

        self.collector.save_prices_to_db("aapl", df)

        data = mock_execute_batch.call_args[0][2]
        self.assertEqual(data[0][0], "AAPL")

    @patch("market.price_fetcher.execute_batch")
    def test_pool_returned_on_exception(self, mock_execute_batch):
        mock_execute_batch.side_effect = Exception("DB write failed")
        df = _make_price_df()

        with self.assertRaises(Exception):
            self.collector.save_prices_to_db("AAPL", df)

        self.mock_pool.putconn.assert_called_once_with(self.mock_conn)

    @patch("market.price_fetcher.execute_batch")
    def test_multiindex_columns_flattened(self, mock_execute_batch):
        """DataFrame with MultiIndex columns should be flattened to field names.

        The code does get_level_values(-1), so field names must be at the last level:
        level 0 = ticker, level 1 = field (matching yfinance per-ticker sub-DataFrame).
        """
        idx = pd.date_range("2025-01-15", periods=1, freq="h", tz="UTC")
        col_index = pd.MultiIndex.from_tuples(
            [
                ("AAPL", "Open"),
                ("AAPL", "High"),
                ("AAPL", "Low"),
                ("AAPL", "Close"),
                ("AAPL", "Volume"),
            ],
            names=["Ticker", "Price"],
        )
        df = pd.DataFrame(
            [[150.0, 155.0, 148.0, 153.0, 1_000_000]], index=idx, columns=col_index
        )

        # Should not raise KeyError
        self.collector.save_prices_to_db("AAPL", df)

        data = mock_execute_batch.call_args[0][2]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0][0], "AAPL")

    @patch("market.price_fetcher.execute_batch")
    def test_correct_ohlcv_values_stored(self, mock_execute_batch):
        df = _make_price_df()

        self.collector.save_prices_to_db("AAPL", df)

        data = mock_execute_batch.call_args[0][2]
        row = data[0]
        self.assertEqual(row[0], "AAPL")  # ticker
        # row[1] is timestamp (datetime)
        self.assertIsInstance(row[1], datetime)
        self.assertEqual(row[2], 150.0)  # open
        self.assertEqual(row[3], 155.0)  # high
        self.assertEqual(row[4], 148.0)  # low
        self.assertEqual(row[5], 153.0)  # close
        self.assertEqual(row[6], 1_000_000)  # volume


# ---------------------------------------------------------------------------
# fetch_and_store_prices
# ---------------------------------------------------------------------------


class TestFetchAndStorePrices(TestPriceCollectorBase):
    def test_calls_fetch_then_save_per_ticker(self):
        df1, df2 = _make_price_df(), _make_price_df()

        with (
            patch.object(
                self.collector,
                "_fetch_hourly_prices",
                return_value={"AAPL": df1, "TSLA": df2},
            ) as mock_fetch,
            patch.object(self.collector, "save_prices_to_db") as mock_save,
        ):
            self.collector.fetch_and_store_prices(["AAPL", "TSLA"], days_back=3)

        mock_fetch.assert_called_once_with(["AAPL", "TSLA"], 3)
        self.assertEqual(mock_save.call_count, 2)
        save_calls = {c[0][0] for c in mock_save.call_args_list}
        self.assertIn("AAPL", save_calls)
        self.assertIn("TSLA", save_calls)

    def test_save_error_does_not_stop_remaining_tickers(self):
        df1, df2 = _make_price_df(), _make_price_df()

        with (
            patch.object(
                self.collector,
                "_fetch_hourly_prices",
                return_value={"AAPL": df1, "TSLA": df2},
            ),
            patch.object(
                self.collector,
                "save_prices_to_db",
                side_effect=[Exception("fail"), None],
            ) as mock_save,
        ):
            # Should not raise
            self.collector.fetch_and_store_prices(["AAPL", "TSLA"])

        self.assertEqual(mock_save.call_count, 2)


# ---------------------------------------------------------------------------
# backfill_prices
# ---------------------------------------------------------------------------


class TestBackfillPrices(TestPriceCollectorBase):
    @patch("market.price_fetcher.helper")
    def test_uses_days_back_window_with_min_mentions_1(self, mock_helper):
        mock_helper.get_active_tickers.return_value = []

        with patch.object(self.collector, "fetch_and_store_prices"):
            self.collector.backfill_prices(days=14)

        args = mock_helper.get_active_tickers.call_args[0]
        start_time = args[1]
        end_time = args[2]
        min_mentions = mock_helper.get_active_tickers.call_args[1].get(
            "min_mentions", args[3] if len(args) > 3 else None
        )

        # start_time should be ~14 days before end_time
        self.assertAlmostEqual(
            (end_time - start_time).total_seconds(),
            timedelta(days=14).total_seconds(),
            delta=5,
        )
        self.assertEqual(min_mentions, 1)

    @patch("market.price_fetcher.helper")
    def test_delegates_to_fetch_and_store(self, mock_helper):
        mock_helper.get_active_tickers.return_value = ["AAPL", "TSLA"]

        with patch.object(self.collector, "fetch_and_store_prices") as mock_fas:
            self.collector.backfill_prices(days=7)

        mock_fas.assert_called_once_with(["AAPL", "TSLA"], days_back=7)

    @patch("market.price_fetcher.helper")
    def test_no_tickers_skips_fetch(self, mock_helper):
        mock_helper.get_active_tickers.return_value = []

        with patch.object(self.collector, "fetch_and_store_prices") as mock_fas:
            self.collector.backfill_prices(days=7)

        mock_fas.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
