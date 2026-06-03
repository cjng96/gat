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
- [x] `gdev ls`는 실행 가능한 명령 목록을 `andBuild serUp ...` 형식의 한 줄로 표시하고 명령은 실행하지 않는다.
- [x] `gdev andBuild serUp`처럼 명령 인자를 여러 개 주면 입력한 순서대로 모두 실행한다.
- [x] 명령 실행이 완료되면 같은 순서로 다시 실행할 수 있는 `gdev ...` 명령줄을 마지막에 표시한다.

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

## 4. Android 설치

- [x] `andInstall`은 ADB에 연결된 모든 설치 가능 장비에 APK를 설치한다.
- [x] `andInstall`은 전체 장비 설치 후 장비 선택 UI를 호출하지 않는다.
- [x] 기존 장비 선택 UI 구현은 유지하되 기본 `andInstall` 경로에서는 사용하지 않는다.
- [x] `andBuild`는 빌드 산출 APK로 `andInstall`을 호출하므로 같은 전체 장비 설치 규칙을 따른다.

## 5. 테스트

- [x] 명령 번호 파싱 순서 검증 (`gdev/tests/test_gdev.py` - `test_command_sequence_parser_maps_numbered_input_in_order`)
- [x] 빈 입력에서 `Space`가 현재 선택 명령 번호와 공백을 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_only_adds_selected_command_when_input_is_empty`)
- [x] 직접 숫자 입력 직후 `Space`가 구분 공백만 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_only_adds_selected_command_when_input_is_empty`)
- [x] 숫자 입력 후 선택 이동 뒤 `Space`가 현재 선택 명령 번호와 공백을 추가하는지 검증 (`gdev/tests/test_gdev.py` - `test_commandInputAfterSpace_adds_selected_command_after_selection_move`)
- [x] 선택 명령 번호 입력 후 수동 숫자 입력이 같은 시퀀스로 파싱되는지 검증 (`gdev/tests/test_gdev.py` - `test_space_selected_command_then_manual_number_parses_in_entered_order`)
- [x] 수동 숫자 입력 후 선택 이동/Space/수동 숫자 입력이 같은 시퀀스로 파싱되는지 검증 (`gdev/tests/test_gdev.py` - `test_manual_number_then_selection_move_space_parses_in_entered_order`)
- [x] 연결된 모든 장비 설치와 선택 UI 미호출 검증 (`gdev/tests/test_gdev.py` - `test_andInstall_installs_all_connected_devices_without_selection`, `test_andInstall_does_not_call_device_selection_ui`)
- [x] 다중 명령 인자 순차 실행과 복붙용 완료 명령 표시 검증 (`gdev/tests/test_gdev.py` - `test_main_runs_multiple_command_arguments_in_order_and_prints_replay`)
- [x] `gdev ls` 명령 목록 한 줄 출력 검증 (`gdev/tests/test_gdev.py` - `test_main_ls_prints_supported_commands_without_running_tasks`)
