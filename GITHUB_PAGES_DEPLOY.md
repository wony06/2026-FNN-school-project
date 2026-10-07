# HYU Menu Guide GitHub Pages 배포

## 현재 상태

- 기존 HTML, CSS, JS, JSON, 계산식과 메뉴 데이터를 수정하지 않는다.
- `main`의 `web/` 폴더를 빌드/데이터 재생성 없이 그대로 배포한다.
- 웹 파일의 상대경로가 저장소 하위 URL에서도 동작하므로 경로 수정은 필요 없다.
- 워크플로가 필요한 웹 파일과 메뉴 사진의 존재 여부를 확인한 뒤 배포한다.
- 배포 전에는 아래 주소가 404일 수 있다. GitHub Actions 성공 후에만 공개 배포 완료로 판단한다.

배포 성공 후 기본 주소:

https://wony06.github.io/2026-FNN-school-project/

`web/` 폴더의 내용 자체를 게시하므로 주소 뒤에 `/web/`을 붙이지 않는다.

## 사용자 설정 (최초 1회)

1. GitHub 저장소의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 선택한다.
   - 설정: https://github.com/wony06/2026-FNN-school-project/settings/pages
   - 설정 권한이 없으면 저장소 관리자에게 이 설정을 요청한다.
   - GitHub Free의 비공개 저장소는 Pages 사용이 제한된다. 해당 안내가 나오면 저장소 공개 여부나 요금제를 관리자가 결정해야 하며, 자동으로 공개 전환하지 않는다.
2. GitKraken에서 `main`에 준비한 배포 파일과 필요한 메뉴 사진을 커밋하고 **Push**한다.
   - 커밋 제목 예: `GitHub Pages 배포 설정 및 누락 메뉴 사진 추가`
   - 워크플로: `.github/workflows/deploy-pages.yml`
   - 안내: `GITHUB_PAGES_DEPLOY.md`
   - 이번 검사에서 기존 웹이 참조하지만 Git에 미등록된 사진 256개가 필요하다. 사진 내용은 변경하지 않는다.
3. GitHub **Actions → Deploy HYU Menu Guide to GitHub Pages**에서 가장 최근 실행이 초록색 성공인지 확인한다.
   - https://github.com/wony06/2026-FNN-school-project/actions
   - Push 전에 Pages 설정을 하지 않아 실패했다면 설정 후 **Re-run all jobs**를 누른다.
   - 수동 실행은 해당 워크플로의 **Run workflow → main → Run workflow**를 사용한다.
4. **Settings → Pages → Visit site** 또는 성공한 배포의 `github-pages` 링크에서 실제 URL을 연다.
   - 사용자 지정 도메인이 설정되어 있으면 GitHub에 표시되는 URL이 최종 기준이다.

## 발표 직전 확인

- 발표 컴퓨터에서 공개 URL을 새로 열고 6월~9월 날짜 선택이 표시되는지 확인한다.
- 사용자 정보를 입력하고 활동수준·영양목표를 선택한 뒤 `내게 맞는 메뉴 보기`를 누른다.
- 추천 결과, 상세 점수, 메뉴 사진을 확인한다.
- 기존 교환단위 미매칭 메뉴는 기존 동작대로 점수가 나오지 않는다. 배포 과정에서 이를 수정하지 않는다.
- 공개 페이지는 GitHub에 마지막으로 Push하여 배포에 성공한 파일을 보여준다. 로컬 Pull만으로 공개 사이트가 바뀌지는 않는다.

## 로컬 사전 확인 결과

- `/2026-FNN-school-project/` 하위 경로에서 첫 화면, 날짜 62일, 메뉴 389개 로딩 확인.
- 테스트 입력: 남성, 만 23세, 175cm, 70kg, 저활동적 (테스트용 가상값).
- 라이프스타일 유지 2700 kcal, 체중감량 2000 kcal, 혈당관리 2700 kcal 선택과 점수 표시 확인.
- 저나트륨·저당·고단백 선택 및 조건 미충족 카드 표시 확인.
- 고단백 선택 시 60.13점의 충족 메뉴가 68.9점의 미충족 메뉴보다 먼저 배치됨을 확인.
- 개인 적합도 49.21/75, NRF 10.92/25, 최종점수 60.13/100 표시 확인.
- PC 1440px 및 모바일 390px에서 입력·결과 레이아웃 확인, 페이지 가로 넘침 없음.
- 브라우저 콘솔 오류 없음.

GitHub 공식 안내: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
