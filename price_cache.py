# -*- coding: utf-8 -*-
"""
해외주식 가격 데이터 캐싱 시스템

yfinance를 사용하여 1년 단위로 CSV 파일에 저장하고,
필요할 때 캐시에서 불러옵니다.
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("yfinance가 설치되지 않았습니다. pip install yfinance 실행해주세요.")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 캐시 디렉토리 설정
CACHE_DIR = Path(__file__).parent / "stocks_info" / "price_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_filename(symbol: str, year: int) -> Path:
    """캐시 파일 경로 반환 (종목/연도.csv 구조)"""
    ticker_dir = CACHE_DIR / symbol.upper()
    ticker_dir.mkdir(parents=True, exist_ok=True)
    return ticker_dir / f"{year}.csv"


def load_from_cache(symbol: str, year: int) -> pd.DataFrame | None:
    """캐시에서 데이터 로드"""
    cache_file = get_cache_filename(symbol, year)
    
    if cache_file.exists():
        logger.info(f"캐시에서 로드: {cache_file.name}")
        # yfinance MultiIndex 헤더 처리 (header=[0,1], skiprows 사용)
        df = pd.read_csv(cache_file, header=[0, 1], index_col=0)
        df.index = pd.to_datetime(df.index)
        # MultiIndex 컬럼을 단일 레벨로 변환 (첫 번째 레벨만 사용)
        df.columns = df.columns.get_level_values(0)
        return df
    return None


def save_to_cache(df: pd.DataFrame, symbol: str, year: int) -> None:
    """데이터를 캐시에 저장"""
    if df.empty:
        logger.warning(f"{symbol} {year}년 데이터가 비어있어 저장하지 않습니다.")
        return
    
    cache_file = get_cache_filename(symbol, year)
    df.to_csv(cache_file)
    logger.info(f"캐시에 저장: {cache_file.name} ({len(df)}개 레코드)")


def fetch_year_data(symbol: str, year: int) -> pd.DataFrame:
    """yfinance로 특정 연도 데이터 다운로드"""
    if not HAS_YFINANCE:
        raise ImportError("yfinance가 필요합니다. pip install yfinance")
    
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # 현재 연도면 오늘까지만
    if year == datetime.now().year:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"yfinance에서 다운로드: {symbol} ({start_date} ~ {end_date})")
    
    df = yf.download(symbol, start=start_date, end=end_date, progress=False)
    
    if df.empty:
        logger.warning(f"{symbol} {year}년 데이터가 없습니다.")
    
    return df


def get_price_data(
    symbol: str,
    start_year: int = 2000,
    end_year: int | None = None,
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    해외주식 가격 데이터를 가져옵니다.
    
    1. 캐시에 있으면 캐시에서 로드
    2. 없으면 yfinance에서 다운로드 후 캐시에 저장
    
    Args:
        symbol: 종목코드 (예: "SPY", "AAPL", "QQQ")
        start_year: 시작 연도 (기본값: 2000)
        end_year: 종료 연도 (기본값: 현재 연도)
        force_refresh: True면 캐시 무시하고 새로 다운로드
        
    Returns:
        DataFrame: OHLCV 데이터
    """
    if end_year is None:
        end_year = datetime.now().year
    
    all_data = []
    
    for year in range(start_year, end_year + 1):
        # 캐시 확인
        if not force_refresh:
            cached_df = load_from_cache(symbol, year)
            if cached_df is not None:
                # 현재 연도면 최신 데이터 업데이트 필요 체크
                if year == datetime.now().year:
                    last_date = cached_df.index.max().date() if len(cached_df) > 0 else None
                    today = datetime.now().date()
                    
                    # 캐시된 마지막 날짜가 어제 이전이면 업데이트
                    if last_date and last_date < today - timedelta(days=1):
                        logger.info(f"현재 연도 데이터 업데이트 필요: {last_date} -> {today}")
                        year_df = fetch_year_data(symbol, year)
                        save_to_cache(year_df, symbol, year)
                        all_data.append(year_df)
                        continue
                
                all_data.append(cached_df)
                continue
        
        # yfinance에서 다운로드
        year_df = fetch_year_data(symbol, year)
        
        if not year_df.empty:
            # 과거 연도 데이터만 캐시 (현재 연도는 계속 업데이트 필요)
            save_to_cache(year_df, symbol, year)
            all_data.append(year_df)
    
    if not all_data:
        return pd.DataFrame()
    
    # 모든 연도 데이터 합치기
    combined_df = pd.concat(all_data)
    combined_df = combined_df.sort_index()
    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]  # 중복 제거
    
    logger.info(f"총 {len(combined_df)}개 레코드 로드 완료")
    logger.info(f"날짜 범위: {combined_df.index.min()} ~ {combined_df.index.max()}")
    
    return combined_df


def list_cached_files(symbol: str | None = None) -> list[str]:
    """캐시된 파일 목록 반환"""
    if symbol:
        ticker_dir = CACHE_DIR / symbol.upper()
        if ticker_dir.exists():
            files = list(ticker_dir.glob("*.csv"))
            return [f"{symbol.upper()}/{f.name}" for f in sorted(files)]
        return []
    else:
        # 모든 종목의 파일 반환
        all_files = []
        for ticker_dir in sorted(CACHE_DIR.iterdir()):
            if ticker_dir.is_dir():
                for f in sorted(ticker_dir.glob("*.csv")):
                    all_files.append(f"{ticker_dir.name}/{f.name}")
        return all_files


def clear_cache(symbol: str | None = None) -> None:
    """캐시 삭제"""
    if symbol:
        ticker_dir = CACHE_DIR / symbol.upper()
        if ticker_dir.exists():
            for f in ticker_dir.glob("*.csv"):
                f.unlink()
                logger.info(f"삭제됨: {symbol.upper()}/{f.name}")
            ticker_dir.rmdir()
    else:
        for ticker_dir in CACHE_DIR.iterdir():
            if ticker_dir.is_dir():
                for f in ticker_dir.glob("*.csv"):
                    f.unlink()
                    logger.info(f"삭제됨: {ticker_dir.name}/{f.name}")
                ticker_dir.rmdir()


# =============================================================================
# 테스트
# =============================================================================
if __name__ == "__main__":
    # 기존 캐시 삭제 후 다시 다운로드
    print("=" * 60)
    print("SPY 가격 데이터 로드 테스트")
    print("=" * 60)
    
    # 기존 캐시 삭제
    clear_cache("SPY")
    
    # SPY 데이터 가져오기
    df = get_price_data("SPY", start_year=2020, end_year=2024)
    
    print("\n데이터 샘플:")
    print(df.tail(10))
    
    print("\n캐시된 파일 목록:")
    for f in list_cached_files():
        print(f"  - {f}")
    
    # 두 번째 실행 - 캐시에서 로드되는지 확인
    print("\n" + "=" * 60)
    print("두 번째 로드 (캐시에서 로드되어야 함)")
    print("=" * 60)
    df2 = get_price_data("SPY", start_year=2020, end_year=2024)
    print(f"로드된 레코드 수: {len(df2)}")
