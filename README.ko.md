<div align="center">

# nlm2obsidian

**Google NotebookLM 노트북을 Obsidian으로 가져오기**

[![Python](https://img.shields.io/badge/python-3.9+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Obsidian](https://img.shields.io/badge/Obsidian-vault-7C3AED?logo=obsidian&logoColor=white)](https://obsidian.md)

*소스, 리포트, 퀴즈, 플래시카드, 마인드맵, 오디오, 영상, 메모, 채팅 기록까지 — 명령어 하나로.*

[English](README.md) | [**한국어**](README.ko.md)

</div>

---

## 이 도구가 하는 일

`nlm2obsidian`은 NotebookLM에 있는 모든 콘텐츠를 가져와서 **Zettelkasten + PARA** 구조에 맞게 Obsidian 볼트에 정리해주는 CLI 도구입니다.

```
NotebookLM                            Obsidian Vault
┌────────────────┐                    ┌──────────────────────────────────────┐
│  소스          │ ──── Literature ──▶│ 5. Zettelkasten/10. Literature/      │
│  리포트        │ ──── Literature ──▶│     NotebookLM/{notebook}/           │
│                │                    │                                      │
│  퀴즈          │ ──── Resource ────▶│ 3. Resources/NotebookLM/{notebook}/  │
│  플래시카드    │ ──── Resource ────▶│                                      │
│  마인드맵      │ ──── Resource ────▶│                                      │
│  미디어 링크   │ ──── Resource ────▶│                                      │
│                │                    │                                      │
│  오디오/영상   │ ──── Binary ──────▶│ 7. Attachments/NotebookLM/{notebook}/│
│  인포그래픽    │ ──── Binary ──────▶│                                      │
│  슬라이드      │ ──── Binary ──────▶│                                      │
│                │                    │                                      │
│  사용자 메모   │ ──── Inbox ───────▶│ 5. Zettelkasten/00. Inbox/           │
│  채팅 기록     │ ──── Inbox ───────▶│     NotebookLM/{notebook}/           │
└────────────────┘                    └──────────────────────────────────────┘
```

### 주요 기능

- **모든 콘텐츠 타입 지원** — 소스, 리포트, 퀴즈, 플래시카드, 마인드맵, 오디오, 영상, 인포그래픽, 슬라이드, 사용자 메모, 채팅 기록
- **Obsidian 네이티브 출력** — YAML 프론트매터, 태그, `![[위키링크]]` 형식의 첨부파일 링크
- **중복 방지** — 동기화 상태 파일로 가져온 항목을 추적해서, 다시 실행해도 이미 가져온 항목은 건너뜀
- **선택적 가져오기** — 노트북 이름(부분 매칭)과 콘텐츠 타입으로 필터링 가능
- **Dry-run 모드** — 파일을 쓰지 않고 어떤 내용이 가져와질지 미리 확인
- **안정적인 오류 처리** — 하나가 실패해도 나머지는 계속 진행하고, 마지막에 실패 목록 출력

---

## 빠른 시작

### 사전 조건

- Python 3.9 이상
- [notebooklm-py](https://pypi.org/project/notebooklm-py/) (자동 설치됨)
- Zettelkasten/PARA 폴더 구조를 갖춘 Obsidian 볼트

### 설치

```bash
cd nlm2obsidian
pip install .
```

### 인증

```bash
nlm2obsidian login
```

브라우저가 열리면서 Google 계정으로 로그인합니다. 세션은 `notebooklm-py`가 로컬에 저장합니다.

### 가져오기

```bash
# 노트북 목록 확인
nlm2obsidian list

# 미리보기 (파일 생성 안 함)
nlm2obsidian import --notebook "AI 연구" --dry-run

# 노트북 하나를 통째로 가져오기
nlm2obsidian import --notebook "AI 연구"

# 모든 노트북에서 소스만 가져오기
nlm2obsidian import --notebook "all" --type sources
```

---

## 명령어

### `nlm2obsidian login`

NotebookLM 접근을 위한 Google 계정 인증.

### `nlm2obsidian list`

모든 노트북을 소스 개수와 함께 표시합니다.

```
Title                                   Sources  ID
────────────────────────────────────────────────────────
AI 논문 스터디                               12  abc123...
독서 노트                                    5  def456...

Total: 2 notebook(s)
```

### `nlm2obsidian import`

핵심 명령어. NotebookLM에서 콘텐츠를 가져와 Obsidian 볼트에 마크다운으로 저장합니다.

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--vault PATH` | `~/Obsidian` | Obsidian 볼트 루트 경로 |
| `--notebook NAME` | *(필수)* | 노트북 이름 (부분 매칭, 대소문자 무시) 또는 `"all"` |
| `--type TYPE` | `all` | `all`, `sources`, `artifacts`, `notes` 중 택 1 |
| `--include-media` | 꺼짐 | 오디오/영상 바이너리 파일 다운로드 |
| `--dry-run` | 꺼짐 | 미리보기만 — 파일 쓰기 없음, 상태 변경 없음 |
| `--force` | 꺼짐 | 이미 동기화된 항목도 다시 가져오기 |
| `-v, --verbose` | 꺼짐 | 항목별 상세 진행 상황 표시 |

**사용 예시:**

```bash
# 이름으로 노트북 지정 (부분 매칭)
nlm2obsidian import --notebook "논문"

# 오디오/영상까지 다운로드
nlm2obsidian import --notebook "팟캐스트" --include-media

# 전부 다시 가져오기 (덮어쓰기)
nlm2obsidian import --notebook "all" --force -v
```

### `nlm2obsidian status`

동기화 현황을 확인합니다.

```
Notebook                             Sources  Artifacts  Notes  Chat   Last Sync
──────────────────────────────────────────────────────────────────────────────────
AI 논문 스터디                            12          3      2   Yes   2026-03-17T10:30:00
독서 노트                                  5          1      0    No   2026-03-17T10:28:00
```

---

## 콘텐츠 매핑

NotebookLM의 각 콘텐츠 타입은 Obsidian 볼트의 적절한 폴더와 노트 형식으로 분류됩니다:

| 콘텐츠 타입 | 저장 경로 | 노트 타입 | 프론트매터 |
|:---|:---|:---:|:---|
| 소스 (AI 요약) | `5. Zettelkasten/10. Literature/` | Literature | `type`, `status`, `created`, `updated`, `source`, `author` |
| 리포트 | `5. Zettelkasten/10. Literature/` | Literature | 위와 동일 |
| 퀴즈 | `3. Resources/` | Resource | `type`, `status`만 |
| 플래시카드 | `3. Resources/` | Resource | `type`, `status`만 |
| 마인드맵 | `3. Resources/` + `7. Attachments/` | Resource | `type`, `status`만 |
| 오디오 / 영상 | `3. Resources/` + `7. Attachments/` | Resource | `type`, `status`만 |
| 인포그래픽 | `3. Resources/` + `7. Attachments/` | Resource | `type`, `status`만 |
| 슬라이드 | `3. Resources/` + `7. Attachments/` | Resource | `type`, `status`만 |
| 사용자 메모 | `5. Zettelkasten/00. Inbox/` | Inbox | `type`, `status`, `created`, `updated`, `source` |
| 채팅 기록 | `5. Zettelkasten/00. Inbox/` | Inbox | 위와 동일 |

> **프론트매터가 다른 이유?**
> Literature와 Inbox 노트는 Zettelkasten 폴더에 저장되기 때문에 날짜 필드로 지식 진화를 추적합니다. Resource 노트는 PARA의 `3. Resources/` 폴더에 들어가는데, 여기서는 Obsidian이 OS 파일 메타데이터를 쓰기 때문에 `created`/`updated` 필드가 필요없습니다.

---

## 동기화 방식

동기화 상태는 볼트 루트의 `.notebooklm-sync.json`에 저장됩니다:

```
Obsidian/
├── .notebooklm-sync.json    <-- 가져온 항목 추적 파일
├── 3. Resources/
│   └── NotebookLM/
│       └── AI 논문 스터디/
│           ├── Quiz - Chapter 1.md
│           └── Flashcards - 핵심 용어.md
├── 5. Zettelkasten/
│   ├── 00. Inbox/
│   │   └── NotebookLM/
│   │       └── AI 논문 스터디/
│   │           ├── 내 메모.md
│   │           └── Chat History.md
│   └── 10. Literature/
│       └── NotebookLM/
│           └── AI 논문 스터디/
│               ├── Attention Is All You Need.md
│               └── Study Guide.md
└── 7. Attachments/
    └── NotebookLM/
        └── AI 논문 스터디/
            ├── Overview.mp4
            └── Mind Map.json
```

- **처음 실행**: 모든 항목을 가져오고 동기화 파일을 생성
- **이후 실행**: 이미 가져온 항목은 건너뜀 (API ID 기준, 파일명 아님)
- **`--force`**: 전부 다시 가져오고 기존 파일 덮어쓰기
- **삭제 없음**: 이 도구는 절대 볼트에서 파일을 삭제하지 않음

---

## 알려진 제한사항

| 제한사항 | 상세 |
|---|---|
| **소스 콘텐츠는 AI 요약만 가능** | NotebookLM API가 소스 전문을 제공하지 않습니다. `get_guide()`를 통한 AI 생성 요약만 가져올 수 있으며, `author` 필드에 "NotebookLM AI Summary"로 명시됩니다. |
| **리포트/퀴즈/플래시카드 파싱은 최선 노력** | 이 콘텐츠들은 문서화되지 않은 API 구조에서 추출합니다. 추출 실패 시 NotebookLM 웹에서 확인하라는 안내가 담긴 플레이스홀더 노트가 생성됩니다. |
| **단방향 가져오기만 지원** | Obsidian에서 수정한 내용은 NotebookLM에 반영되지 않습니다. |
| **단일 사용자용** | 하나의 볼트, 하나의 NotebookLM 계정 기준으로 설계되었습니다. |
| **자동 동기화 없음** | 필요할 때 수동으로 실행합니다. 백그라운드 데몬이나 cron은 없습니다. |

---

## 아키텍처

```
cli.py              Click CLI — 인자 파싱, asyncio.run() 래핑
    │
    ▼
importer.py         노트북별 가져오기 오케스트레이션, 콘텐츠 타입별 라우팅
    │
    ├──▶ formatters.py     순수 함수: 마크다운 생성, 프론트매터, 태그
    ├──▶ raw_parser.py     API raw 데이터에서 리포트/퀴즈/플래시카드 텍스트 추출
    └──▶ sync_state.py     볼트 루트에 JSON 기반 중복 추적
```

---

## 라이선스

MIT
