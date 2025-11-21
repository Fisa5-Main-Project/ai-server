-- H2 데이터베이스는 기본적으로 JSON 타입을 지원하지 않으므로, 관련 정보는 TEXT 타입 컬럼에 JSON 형식의 문자열로 저장합니다.

-- financial_product (기존 데이터 유지)
INSERT INTO financial_product (product_name, product_type, bank_name, min_amount, max_amount, min_period_months, max_period_months, base_interest_rate, interest_rate_details, bonus_rate_details, compounding_strategy, applicable_tendency)
VALUES (
    'WON플러스 예금',
    'DEPOSIT',
    '우리은행',
    10000,
    NULL, -- No max amount
    1,
    36,
    NULL, -- Tiered rates are used instead of a single base rate
    '{
        "tiers": [
            {"months_gte": 1, "months_lt": 3, "rate": 2.55},
            {"months_gte": 3, "months_lt": 6, "rate": 2.60},
            {"months_gte": 6, "months_lt": 12, "rate": 2.75},
            {"months_gte": 12, "months_lt": 13, "rate": 2.80},
            {"months_gte": 13, "months_lt": 24, "rate": 2.70},
            {"months_gte": 24, "months_lt": 37, "rate": 2.40}
        ]
    }',
    NULL, -- No bonus rates
    'SIMPLE',
    '원금보존형'
);

INSERT INTO financial_product (product_name, product_type, bank_name, min_amount, max_amount, min_period_months, max_period_months, base_interest_rate, interest_rate_details, bonus_rate_details, compounding_strategy, applicable_tendency)
VALUES (
           '우리 SUPER주거래 적금',
           'SAVINGS',
           '우리은행',
           NULL, -- 최소 가입금액 없음
           500000, -- 월 최대 50만원
           12, -- 1년
           36, -- 3년
           2.15, -- 기본금리 (1년~3년 모두 2.15%)
           NULL, -- 기간별 기본금리가 동일하므로 details 생략
           '{
               "conditions": [
                   {"name": "급여이체 또는 연금이체 실적 (계약기간 1/2 이상)", "rate": 0.7},
                   {"name": "공과금 자동이체 실적 (계약기간 1/2 이상)", "rate": 0.3},
                   {"name": "우리카드(신용/체크) 결제계좌 지정 및 사용실적 (월 10만원 이상)", "rate": 0.3},
                   {"name": "마케팅 동의(전화 및 SMS) 유지", "rate": 0.1}
               ]
           }',
           'SIMPLE',
           '위험중립형'
       );

-- Term (기존 데이터 유지)
INSERT INTO term (is_required, term_name) VALUES (true, '서비스 이용약관');
INSERT INTO term (is_required, term_name) VALUES (true, '개인정보 수집 및 이용 동의');
INSERT INTO term (is_required, term_name) VALUES (false, '마케팅 정보 수신 동의');

-- Keyword (기존 데이터 유지)
INSERT INTO keyword (name) VALUES ('안정적 생활비');
INSERT INTO keyword (name) VALUES ('목돈 마련');
INSERT INTO keyword (name) VALUES ('비상금 확보');
INSERT INTO keyword (name) VALUES ('증여/상속');
INSERT INTO keyword (name) VALUES ('대출 상환');
INSERT INTO keyword (name) VALUES ('여행');
INSERT INTO keyword (name) VALUES ('가족/교류');
INSERT INTO keyword (name) VALUES ('고급 취미');
INSERT INTO keyword (name) VALUES ('반려동물');
INSERT INTO keyword (name) VALUES ('귀농/귀촌');
INSERT INTO keyword (name) VALUES ('창업/사업');
INSERT INTO keyword (name) VALUES ('재취업/소일거리');
INSERT INTO keyword (name) VALUES ('자기계발');
INSERT INTO keyword (name) VALUES ('봉사/사회공헌');
INSERT INTO keyword (name) VALUES ('건강/의료비');
INSERT INTO keyword (name) VALUES ('편안한 휴식');

-- Dummy Asset Data for user_id = 1 (testuser1)
-- user_id 1은 AuthService.initTestUser()에서 생성됩니다.
INSERT INTO assets (user_id, type, balance, bank_code) VALUES
(1, 'CURRENT', 5000000, '004'),
(1, 'SAVING', 1200000, '004'),
(1, 'INVEST', 25000000, NULL),
(1, 'PENSION', 150000000, NULL),
(1, 'AUTOMOBILE', 30000000, NULL),
(1, 'REAL_ESTATE', 800000000, NULL),
(1, 'LOAN', -300000000, NULL);

-- Dummy Pension Data for user_id = 1 (linked to the PENSION asset above)
INSERT INTO pension (asset_id, updated_at, pension_type, account_name, principal, personal_contrib, contrib_year, total_personal_contrib) VALUES
((SELECT asset_id FROM assets WHERE user_id = 1 AND type = 'PENSION' LIMIT 1), NOW(), 'DC', '우리은행 개인형IRP', 150000000.00, 10000000.00, 2023, 50000000.00);
