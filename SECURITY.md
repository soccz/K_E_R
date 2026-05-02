# 보안 정책

이 시스템은 GitHub 레포 + Claude API + DART API + 로컬 파일시스템에 걸쳐 동작한다.
다음 규칙을 *반드시* 따른다.

## 1. 절대 커밋하지 말 것

| 파일 | 내용 | 보호 |
|---|---|---|
| `.env` | DART/Anthropic API 키 | `.gitignore`에 등록 |
| `*.key`, `*.pem`, `*.p12` | 개인키·인증서 | `.gitignore` |
| `secrets/`, `credentials/` | 자격증명 디렉토리 | `.gitignore` |
| `.anthropic*`, `.claude/` | Claude Code 세션 | `.gitignore` |
| `*.log` | 로그 (URL·키 leak 가능) | `.gitignore` |
| `pipeline/cache/CORPCODE.xml` | DART 마스터 (대용량) | `.gitignore` |
| `companies/**/raw_inputs/dart_filings/*.pdf` | 원본 PDF (대용량) | `.gitignore` |

## 2. 키 관리

### DART OpenAPI 키
- 발급: opendart.fss.or.kr → 인증키 신청 (40자 영문/숫자)
- 보관: `.env` 파일 (`DART_API_KEY=...`)
- 권한: `chmod 600 .env` 필수 (다른 사용자 read 차단)
- 분실/leak 시: opendart 마이페이지 → 키 재발급 → `.env` 갱신

### Anthropic 구독 (Claude Code CLI)
- 인증 위치: `~/.claude/` 또는 OS keychain (Claude Code가 관리)
- API 키 *불필요* (구독 모드)
- `~/.claude/`도 `.gitignore`에 등록되어 있음 (혹시 모를 백업 commit 방지)

### Anthropic API 키 (옵션)
- 사용 케이스: `LLM_PROVIDER=anthropic`로 전환할 때만
- 발급: console.anthropic.com → API Keys
- 보관: `.env` (`ANTHROPIC_API_KEY=sk-ant-...`)
- Leak 시: console에서 즉시 revoke

### GitHub 자격증명
- SSH 키 (`~/.ssh/`) 또는 PAT (Personal Access Token) 사용
- PAT는 *최소 권한* (`repo` scope만, full admin No)
- 만료기간 90일 이내 권장

## 3. 코드 안전 패턴

### DartClient
- 모든 API 호출 시 `crtfc_key` 가 URL에 포함됨 (DART API 한계)
- 에러 메시지에 키가 들어가지 않도록 `_redact()` 함수 사용
- 디버그 로깅·verbose 모드 활성화 시 직접 점검할 것

### LLM 호출 (Claude Code CLI)
- 시스템 프롬프트는 임시 파일로 전달 (`--system-prompt-file`)
- 임시 파일은 `chmod 0o600` (owner-only)
- 호출 후 즉시 unlink
- TMPDIR이 user-private 폴더(`/home/soccz/22tb/tmp`)인지 확인

### 보고서·프롬프트 스냅샷
- `companies/**/raw_inputs/prompts/` 는 commit됨 (audit trail 목적)
- 프롬프트 안에 키 없음을 보장 (`pipeline/security_check.py`로 검증)

## 4. GitHub 레포 정책

이 레포는 **반드시 private**으로 유지한다. 이유:
- `_persona.md` — 사용자의 *개인 투자 철학·관점* (PII 아니지만 사회공학 벡터)
- 보고서는 사용자의 *투자 추적 대상*을 노출 (24종목 + 분석 깊이)

만약 public 전환 시:
- `_persona.md`를 generic 버전으로 교체
- `_watchlist.md`도 익명화
- 보고서 폴더는 별도 private 미러로 분리

## 5. 커밋 전 체크리스트

```bash
# 1. secret 스캐너 실행
python -m pipeline.security_check

# 2. .env 변경 사항 없는지 확인
git status | grep -E "\.env"  # 비어있어야 함

# 3. 의심스러운 추가 파일 없는지 점검
git diff --cached --name-only

# 4. commit
git commit -m "..."
```

## 6. Claude API에 무엇이 보내지는지 인지

매 섹션 생성 시 다음 데이터가 Anthropic 인프라로 전송됨:
- `_frame.md` (분석 프레임)
- `_persona.md` (**사용자 투자 철학 — 개인적**)
- 해당 섹션 spec
- 회사명·DART 데이터 (공개 정보)
- 시장 데이터 (공개 정보)

수용 가능한 위험:
- Anthropic 구독 모드는 기본적으로 *학습에 사용 안 됨* (Anthropic 정책)
- 그러나 *infrastructure 처리*는 일어남 — 완전 차단 원하면 zero-retention agreement 검토

원치 않는 케이스:
- `_persona.md`에 PII (실명·계좌·주소 등) 절대 적지 말 것
- 분석 보고서에 본인 보유 종목 수량·매수가 적지 말 것

## 7. 로컬 파일 권한 권장

```bash
chmod 600 .env                              # 키 파일
chmod 700 /home/soccz/22tb/report/          # 레포 루트
chmod 700 /home/soccz/22tb/tmp/             # 임시 파일 디렉토리
```

## 8. Leak 발생 시 대응

키 leak 의심 시:
1. **즉시 rotate** (DART/Anthropic/GitHub 모두)
2. git history에서 제거 (`git filter-repo --invert-paths --path .env`)
3. `git push --force` (단, 협업자 있으면 사전 협의)
4. GitHub Security tab 확인 (자동 secret scan 결과)

## 9. 정기 점검 (분기 1회 권장)

- [ ] DART 키 사용량 확인 (DART 마이페이지)
- [ ] Anthropic API 사용량 확인 (console)
- [ ] `pipeline/security_check.py --all` 실행
- [ ] GitHub repo settings → Security 탭 확인
- [ ] `.env` 파일 권한 600 유지 확인
