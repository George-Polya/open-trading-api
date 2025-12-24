# -*- coding: utf-8 -*-
"""
SPY ETF 가격 조회 테스트
KIS API를 사용하여 SPY의 일봉 데이터를 가져옵니다.
"""

import sys
import logging
import time

import pandas as pd

sys.path.extend(['examples_llm'])

import kis_auth as ka
from overseas_stock.dailyprice.dailyprice import dailyprice

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # pandas 출력 옵션 설정
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_rows', 50)

    # 인증 (모의투자)
    logger.info("토큰 발급 중...")
    ka.auth(svr='vps')
    logger.info("토큰 발급 완료")
    
    # Rate limit 방지를 위해 잠시 대기
    time.sleep(1)

    # SPY 일봉 조회
    # SPY는 NYSE Arca (AMEX)에 상장 - excd="AMS"
    logger.info("SPY 일봉 데이터 조회 시작...")
    
    df1, df2 = dailyprice(
        auth="",
        excd="AMS",       # AMEX (NYSE Arca)
        symb="SPY",       # SPY ETF
        gubn="0",         # 0: 일봉, 1: 주봉, 2: 월봉
        bymd="",          # 비워두면 최신 데이터부터
        modp="1",         # 1: 수정주가 반영
        env_dv="demo",    # 모의투자
        max_depth=3       # 약 300일치만 조회 (rate limit 방지)
    )

    # 결과 출력
    logger.info("=== 조회 결과 ===")
    
    if df1 is not None and not df1.empty:
        logger.info("output1 (기본정보):")
        print(df1)
    
    if df2 is not None and not df2.empty:
        logger.info(f"\noutput2 (일봉 데이터) - 총 {len(df2)}개 레코드:")
        print(df2.head(20))  # 처음 20개만 출력
        
        # 날짜 범위 확인
        if 'xymd' in df2.columns:
            logger.info(f"\n날짜 범위: {df2['xymd'].min()} ~ {df2['xymd'].max()}")
    else:
        logger.warning("조회된 데이터가 없습니다.")

if __name__ == "__main__":
    main()
