# gdev Spec

`gdev`는 프로젝트 루트의 `gat_dev.py`를 실행하는 개발/빌드 보조 도구다.
공통 빌드 로직은 `gdev` 패키지가 제공하고, 각 프로젝트는 `GatDev`를 상속해
필요한 `cmdXxx()` 메서드와 설정만 선언한다.

## 1. 프로젝트 명령 선언

- [x] 프로젝트 명령은 `gat_dev.py`의 `GatDev` 하위 클래스에 정의한 `cmdXxx()` 메서드로 선언한다.
- [x] 명령 이름은 `cmdXxx()`에서 앞의 `cmd`를 제거하고 첫 글자를 소문자로 바꾼 값이다.
  - 예: `cmdAndBuild()` -> `andBuild`
  - 예: `cmdMacFfiRestore()` -> `macFfiRestore`
- [x] 명령 표시 순서는 최종 프로젝트 클래스에 정의된 `cmdXxx()` 메서드 순서를 따른다.
- [x] `GatDevBase`의 기본 `cmdXxx()` 메서드는 재사용 가능한 기본 구현만 제공하며, 프로젝트 클래스가 직접 오버라이드하지 않으면 명령으로 노출하지 않는다.
- [x] 프로젝트 클래스는 커스터마이징이 필요 없는 명령도 `cmdXxx()`에서 `super().cmdXxx()`를 호출해 명시적으로 노출할 수 있다.

## 2. 설정 구조

- [x] 공통 경로 설정은 `GatDev.PathCfg`로 선언한다.
- [x] Android, desktop, SSH 공통 설정은 각각 `AndroidCfg`, `DesktopCfg`, `SshCfg`를 사용한다.
- [x] `PathCfg.root`는 기본적으로 프로젝트 `gat_dev.py`가 있는 디렉토리로 추론한다.
- [x] `PathCfg`의 경로 필드는 생성 시 문자열로 받을 수 있고, 실행 시 프로젝트 root 기준 절대 `Path`로 변환한다.
- [x] 기존 flat 설정 필드(`androidDriveTarget`, `sshDeployHost` 등)는 하위 호환을 위해 유지한다.

## 3. TTY 명령 선택 UI

`gdev`를 TTY에서 명령 인자 없이 실행하면 번호 기반 명령 선택 UI를 연다.

- [x] `Up`/`Down` 또는 `k`/`j`로 현재 선택 명령을 이동한다.
- [x] 숫자 키로 명령 번호를 직접 입력할 수 있다.
- [x] 입력란이 비어 있을 때 `Space`를 누르면 현재 선택 명령 번호와 뒤따르는 공백을 입력한다.
  - 예: 세 번째 명령 선택 상태에서 `Space` -> `3 `
- [x] 숫자를 직접 입력한 직후 `Space`를 누르면 현재 선택 명령을 추가하지 않고 구분 공백만 입력한다.
  - 예: `3` 입력 후 `Space` -> `3 `
- [x] 숫자가 입력된 상태에서도 `Up`/`Down` 또는 `k`/`j`로 선택을 이동한 뒤 `Space`를 누르면 이동 후 현재 선택 명령 번호와 뒤따르는 공백을 추가한다.
  - 예: `3` 입력 후 첫 번째 명령으로 이동하고 `Space` -> `3 1 `
- [x] `Enter`는 입력된 명령 번호를 입력 순서대로 해석해 실행한다.

## 4. 테스트

- [x] 명령 번호 파싱 순서 검증 (`gdev/tests/test_gdev.py` - `test_command_sequence_parser_maps_numbered_input_in_order`)
- [x] 빈 입력에서 `Space`가 현재 선택 명령 번호와 공백을 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_only_adds_selected_command_when_input_is_empty`)
- [x] 직접 숫자 입력 직후 `Space`가 구분 공백만 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_only_adds_selected_command_when_input_is_empty`)
- [x] 숫자 입력 후 선택 이동 뒤 `Space`가 현재 선택 명령 번호와 공백을 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_adds_selected_command_after_selection_move`)
- [x] 선택 명령 번호 입력 후 수동 숫자 입력이 같은 시퀀스로 파싱되는지 검증 (`gdev/tests/test_gdev.py` - `test_space_selected_command_then_manual_number_parses_in_entered_order`)
- [x] 수동 숫자 입력 후 선택 이동/Space/수동 숫자 입력이 같은 시퀀스로 파싱되는지 검증 (`gdev/tests/test_gdev.py` - `test_manual_number_then_selection_move_space_parses_in_entered_order`)
