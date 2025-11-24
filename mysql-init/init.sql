-- ---------------------------------
-- 1. 데이터베이스 생성
-- ---------------------------------
CREATE DATABASE IF NOT EXISTS main_db;
USE main_db;

-- ---------------------------------
-- 2. 테이블 생성 (오류 수정됨)
-- ---------------------------------

-- (1) users: PK AI, VARCHAR 길이, UNIQUE 제약조건 수정
CREATE TABLE `users` (
	`user_id`	INT	NOT NULL AUTO_INCREMENT,
	`login_id`	VARCHAR(100) NOT NULL UNIQUE,
	`password`	VARCHAR(255) NOT NULL,
	`phone_num`	VARCHAR(20) NOT NULL,
	`birth`	DATE	NOT NULL	COMMENT '1990-01-01',
	`gender`	ENUM('F','M')	NOT NULL,
	`name`	VARCHAR(50)	NOT NULL,
	`job`	VARCHAR(100)	NOT NULL,
	`asset_total`	BIGINT	NULL,
    PRIMARY KEY (`user_id`)
);

-- (2) term: PK AI, VARCHAR 길이 수정
CREATE TABLE `term` (
	`term_id`	INT	NOT NULL AUTO_INCREMENT,
	`term_name`	VARCHAR(255) NOT NULL,
	`is_required`	BOOLEAN	NOT NULL,
	`term_content`	TEXT NOT NULL, -- VARCHAR 대신 TEXT
    PRIMARY KEY (`term_id`)
);

-- (3) keywords: PK AI, VARCHAR 길이, UNIQUE 제약조건 추가
CREATE TABLE `keywords` (
	`keyword_id`	INT	NOT NULL AUTO_INCREMENT,
	`category`	ENUM('재정/자산', '여가/관계', '성취/개발', '건강/안정')	NOT NULL,
	`keyword_name`	VARCHAR(50)	NOT NULL UNIQUE COMMENT '목돈마련, 자기계발 등',
    PRIMARY KEY (`keyword_id`)
);

-- (4) users_info: PK AI, annual_income BIGINT, investment_tendancy NULL 허용
CREATE TABLE `users_info` (
	`user_info_id`	INT	NOT NULL AUTO_INCREMENT,
	`user_id`	INT	NOT NULL,
	`target_retired_age`	INT	NOT NULL,
	`goal_amount`	BIGINT	NOT NULL,
	`goal_period`	INT	NOT NULL,
	`expectation_monthly_cost`	INT	NOT NULL,
	`fixed_monthly_cost`	INT	NOT NULL,
	`num_dependents`	INT	NOT NULL,
	`annual_income`	BIGINT	NOT NULL, -- INT -> BIGINT
	`mydata_status`	ENUM('NONE', 'LINKED', 'EXPIRED', 'REVOKED')	NOT NULL	DEFAULT 'NONE',
	`mydata_linked_at`	DATETIME	NULL,
	`investment_tendancy`	ENUM('공격투자형', '적극투자형', '위험중립형', '안정추구형', '원금보존형') NULL, -- NOT NULL -> NULL
    PRIMARY KEY (`user_info_id`)
);

-- (5) MyData: user_ registration 오타 수정, VARCHAR 길이 수정
CREATE TABLE `MyData` (
	`user_id`	INT	NOT NULL,
	`user_registration`	Boolean	NOT NULL, -- 오타 수정
	`user_access_token`	TEXT NULL, -- VARCHAR -> TEXT
	`user_refresh_token`	TEXT NULL, -- VARCHAR -> TEXT
	`user_ci`	VARCHAR(255) NULL	COMMENT '암호화 되어서 저장',
    PRIMARY KEY (`user_id`)
);

-- (66) assets: PK AI, ENUM 쉼표 오류 수정, VARCHAR 길이 수정
CREATE TABLE `assets` (
	`asset_id`	INT	NOT NULL AUTO_INCREMENT,
	`user_id`	INT	NOT NULL,
	`balance`	BIGINT	NOT NULL,
	`bank_code`	VARCHAR(50)	NULL,
	`type`	ENUM('CURRENT', 'SAVINGS', 'INVEST', 'PENSION','AUTOMOBILE','REAL-ESTATE','LOAN')	NULL, -- 쉼표 제거
    PRIMARY KEY (`asset_id`)
);

-- (7) pension: VARCHAR 길이 수정
CREATE TABLE `pension` (
	`asset_id`	INT	NOT NULL,
	`updated_at`	DATETIME	NULL	COMMENT '업데이트 날짜',
	`pension_type`	ENUM('DB', 'DC', 'IRP')	NULL,
	`account_name`	VARCHAR(255) NOT NULL,
	`income_avg_3m`	DECIMAL(15,2)	NULL,
	`working_date`	INT	NULL	COMMENT '근속년수 (DB)',
	`principal`	DECIMAL(15,2)	NULL,
	`company_contrib`	DECIMAL(15,2)	NULL,
	`personal_contrib`	DECIMAL(15,2)	NULL,
	`contrib_year`	INT	NULL,
	`total_personal_contrib`	DECIMAL(15,2)	NULL,
    PRIMARY KEY (`asset_id`)
);

-- (8) user_keyword_map: PK 정의
CREATE TABLE `user_keyword_map` (
	`keyword_id`	INT	NOT NULL,
	`user_id`	INT	NOT NULL,
    PRIMARY KEY (`user_id`, `keyword_id`)
);

-- (9) users_term: PK 정의
CREATE TABLE `users_term` (
	`user_id`	INT	NOT NULL,
	`term_id`	INT	NOT NULL,
	`is_agreed`	BOOLEAN	NULL,
	`agreed_at`	DATETIME	NULL,
    PRIMARY KEY (`user_id`, `term_id`)
);


-- ---------------------------------
-- 3. 외래 키 (FK) 설정 (누락된 키 추가)
-- ---------------------------------
ALTER TABLE `users_info` ADD CONSTRAINT `FK_users_TO_users_info_1` FOREIGN KEY (
	`user_id`
)
REFERENCES `users` (
	`user_id`
);

ALTER TABLE `user_keyword_map` ADD CONSTRAINT `FK_users_TO_user_keyword_map_1` FOREIGN KEY (
	`user_id`
)
REFERENCES `users` (
	`user_id`
);

ALTER TABLE `user_keyword_map` ADD CONSTRAINT `FK_keywords_TO_user_keyword_map_1` FOREIGN KEY (
	`keyword_id`
)
REFERENCES `keywords` (
	`keyword_id`
);

ALTER TABLE `users_term` ADD CONSTRAINT `FK_users_TO_users_term_1` FOREIGN KEY (
	`user_id`
)
REFERENCES `users` (
	`user_id`
);

ALTER TABLE `users_term` ADD CONSTRAINT `FK_term_TO_users_term_1` FOREIGN KEY (
	`term_id`
)
REFERENCES `term` (
	`term_id`
);

ALTER TABLE `assets` ADD CONSTRAINT `FK_users_TO_assets_1` FOREIGN KEY (
	`user_id`
)
REFERENCES `users` (
	`user_id`
);

ALTER TABLE `pension` ADD CONSTRAINT `FK_assets_TO_pension_1` FOREIGN KEY (
	`asset_id`
)
REFERENCES `assets` (
	`asset_id`
);

ALTER TABLE `MyData` ADD CONSTRAINT `FK_users_TO_MyData_1` FOREIGN KEY (
	`user_id`
)
REFERENCES `users` (
	`user_id`
);

-- ---------------------------------
-- 4. Mock Data 생성
-- ---------------------------------

-- (1) 마스터 데이터: 키워드
INSERT INTO `keywords` (`keyword_id`, `category`, `keyword_name`) VALUES
(1, '재정/자산', '안정적 생활비'),
(2, '재정/자산', '목돈 마련'),
(3, '재정/자산', '비상금 확보'),
(4, '재정/자산', '증여/상속'),
(5, '재정/자산', '대출 상환'),
(6, '여가/관계', '여행'),
(7, '여가/관계', '가족/교류'),
(8, '여가/관계', '고급 취미'),
(9, '여가/관계', '반려동물'),
(10, '여가/관계', '귀농/귀촌'),
(11, '성취/개발', '창업/사업'),
(12, '성취/개발', '재취업/소일거리'),
(13, '성취/개발', '자기계발'),
(14, '성취/개발', '봉사/사회공헌'),
(15, '건강/안정', '건강/의료비'),
(16, '건강/안정', '편안한 휴식');

-- (2) 유저 1: 이종혁 (30세, 개발자, 공격투자형)
INSERT INTO `users` (`user_id`, `login_id`, `password`, `phone_num`, `birth`, `gender`, `name`, `job`, `asset_total`) 
VALUES (1, 'lee123', 'hashed_password_123', '010-1111-2222', '1995-01-01', 'M', '이종혁', '개발자', 50000000);

-- 유저 1의 부가 정보 (공격투자형)
INSERT INTO `users_info` (`user_id`, `target_retired_age`, `goal_amount`, `goal_period`, `expectation_monthly_cost`, `fixed_monthly_cost`, `num_dependents`, `annual_income`, `investment_tendancy`) 
VALUES (1, 60, 1000000000, 30, 3000000, 1000000, 0, 70000000, '공격투자형');

-- 유저 1의 키워드 (목돈 마련, 여행, 창업/사업)
INSERT INTO `user_keyword_map` (`user_id`, `keyword_id`) VALUES (1, 2), (1, 6), (1, 11);

-- 유저 1의 자산
INSERT INTO `assets` (`user_id`, `balance`, `bank_code`, `type`) 
VALUES (1, 50000000, '088', 'INVEST'); -- 투자 자산 5천만원

-- 유저 1의 마이데이터
INSERT INTO `MyData` (`user_id`, `user_registration`, `user_ci`) 
VALUES (1, TRUE, 'ci_lee_123abc...');


-- (3) 유저 2: 김민지 (45세, 디자이너, 안정추구형)
INSERT INTO `users` (`user_id`, `login_id`, `password`, `phone_num`, `birth`, `gender`, `name`, `job`, `asset_total`) 
VALUES (2, 'kim456', 'hashed_password_456', '010-3333-4444', '1980-05-10', 'F', '김민지', '디자이너', 120000000);

-- 유저 2의 부가 정보 (안정추구형)
INSERT INTO `users_info` (`user_id`, `target_retired_age`, `goal_amount`, `goal_period`, `expectation_monthly_cost`, `fixed_monthly_cost`, `num_dependents`, `annual_income`, `investment_tendancy`) 
VALUES (2, 65, 500000000, 20, 4000000, 1500000, 1, 80000000, '안정추구형');

-- 유저 2의 키워드 (안정적 생활비, 건강/의료비)
INSERT INTO `user_keyword_map` (`user_id`, `keyword_id`) VALUES (2, 1), (2, 15);

-- 유저 2의 자산
INSERT INTO `assets` (`user_id`, `balance`, `bank_code`, `type`) 
VALUES (2, 120000000, '020', 'SAVINGS'); -- 예금 1억 2천

-- 유저 2의 마이데이터
INSERT INTO `MyData` (`user_id`, `user_registration`, `user_ci`) 
VALUES (2, TRUE, 'ci_kim_456def...');