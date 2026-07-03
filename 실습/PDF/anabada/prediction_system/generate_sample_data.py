"""테스트용 예시 CSV 데이터 생성 스크립트."""

import os

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "raw", "sample_sales_data.csv")


def generate_sample_data(n_rows: int = 200) -> pd.DataFrame:
    """매출 예측용 샘플 데이터 생성."""
    np.random.seed(42)

    regions = ["서울", "부산", "대구", "인천", "광주"]
    products = ["전자", "식품", "의류", "가구"]

    광고비 = np.random.uniform(100, 5000, n_rows)
    인력수 = np.random.randint(5, 100, n_rows)
    생산량 = np.random.uniform(500, 10000, n_rows)
    원가 = np.random.uniform(200, 8000, n_rows)
    지역 = np.random.choice(regions, n_rows)
    제품군 = np.random.choice(products, n_rows)

    매출 = (
        50
        + 2.5 * 광고비
        + 30 * 인력수
        + 0.8 * 생산량
        - 0.5 * 원가
        + np.random.normal(0, 200, n_rows)
    )

    df = pd.DataFrame(
        {
            "매출": 매출,
            "광고비": 광고비,
            "인력수": 인력수,
            "생산량": 생산량,
            "원가": 원가,
            "지역": 지역,
            "제품군": 제품군,
        }
    )

    # 결측치 추가 (약 5%)
    missing_indices = np.random.choice(n_rows, size=int(n_rows * 0.05), replace=False)
    for idx in missing_indices[: len(missing_indices) // 2]:
        df.loc[idx, "광고비"] = np.nan
    for idx in missing_indices[len(missing_indices) // 2 :]:
        df.loc[idx, "생산량"] = np.nan

    # 이상치 추가
    outlier_indices = np.random.choice(n_rows, size=5, replace=False)
    df.loc[outlier_indices[0], "광고비"] = df["광고비"].max() * 3
    df.loc[outlier_indices[1], "생산량"] = df["생산량"].max() * 2.5
    df.loc[outlier_indices[2], "원가"] = df["원가"].max() * 2
    df.loc[outlier_indices[3], "매출"] = df["매출"].max() * 2
    df.loc[outlier_indices[4], "인력수"] = df["인력수"].max() * 2

    return df


if __name__ == "__main__":
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    sample_df = generate_sample_data()
    sample_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"샘플 데이터 생성 완료: {OUTPUT_PATH}")
    print(f"행 수: {len(sample_df)}, 열 수: {len(sample_df.columns)}")
    print(f"컬럼: {list(sample_df.columns)}")
