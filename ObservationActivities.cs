using System;
using System.Collections.Generic;
using System.Linq;

public sealed record ObservationActivity(string Action, string RereReaction);

public static class ObservationActivities
{
    private static readonly Dictionary<string, ObservationActivity[]> BySkillWithOtherCharacter =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["관찰력"] = Set(
                ("[[RERE_PARTNER_OBJECT]] 빤히 바라보고 있어요. 신경 쓰이는 게 있나 봐요!", "뭘까요? 레레도 볼래요!"),
                ("[[RERE_PARTNER_OBJECT]] 바라보다가 잠시 시선을 돌리고 있어요. 뭔가 눈에 띄었나 봐요!", "레레도 무슨 일인지 궁금해졌어요!")
            ),
            ["듣기"] = Set(
                ("[[RERE_PARTNER_OBJECT]] 바라보며 조용히 이야기에 귀를 기울이고 있어요.", "흥미로운 이야기가 오가나 봐요!"),
                ("[[RERE_PARTNER_GENITIVE]] 말소리가 들리는 쪽으로 살짝 고개를 기울이고 있어요.", "무슨 이야긴지 레레도 궁금해요!")
            ),
            ["심리학"] = Set(
                ("[[RERE_PARTNER_GENITIVE]] 표정과 말투를 가만히 살펴보고 있어요.", "무슨 생각을 하는지 궁금한가 봐요!"),
                ("[[RERE_PARTNER_OBJECT]] 바라보며 말과 표정이 어떻게 달라지는지 살펴보고 있어요.", "상대방이 진심인지 알고싶은가봐요!")
            ),
            ["정신분석"] = Set(
                ("[[RERE_PARTNER_GENITIVE]] 표정에 잠시 시선을 두고 있어요.", "무슨 일이 있었나봐요."),
                ("[[RERE_PARTNER_OBJECT]] 바라보며 기분을 살피고 있나봐요.", "부탁하고 싶은 일이라도 있는걸까요?")
            ),
            ["말재주"] = Set(
                ("[[RERE_PARTNER_GENITIVE]] 반응을 살피며 재치 있는 말을 이어가고 있어요.", "이야기에 관심이 가나 봐요!"),
                ("재치 있게 대답하며 대화를 이어가고 있어요. [[RERE_PARTNER]]도 귀를 기울이고 있네요.", "어떤 이야기가 이어질지 궁금해요!")
            ),
            ["예술/공예"] = Set(
                ("작은 소품의 모양을 조금씩 다듬고 있어요. [[RERE_PARTNER]]도 옆에서 조용히 지켜보고 있네요.", "무엇이 완성될지 궁금한가 봐요!"),
                ("종이에 떠오른 모양을 가볍게 스케치하고 있어요. [[RERE_PARTNER]]의 시선도 그림을 따라가네요.", "레레도 옆에서 구경하고 싶어요!")
            ),
            ["자료조사"] = Set(
                ("필요한 자료를 찾아 내용을 메모하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 메모를 따라가네요.", "어떤 내용을 찾았는지 레레도 궁금해요!"),
                ("자료를 비교하며 필요한 정보를 정리하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 책장을 따라 움직이네요.", "차근차근 살펴보면 답이 보이나 봐요!")
            ),
            ["언어"] = Set(
                ("사전과 메모를 번갈아 보며 문장을 해석하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 책장을 따라가네요.", "낯선 문장도 하나씩 알아가고 있네요!"),
                ("낯선 문장을 소리 내어 읽으며 발음을 익히고 있어요. [[RERE_PARTNER_GENITIVE]] 귀에도 또렷이 들리나 봐요.", "레레도 같이 따라 읽어볼래요!")
            ),
            ["설득"] = Set(
                ("상대가 이해하기 쉽게 의견을 차분히 설명하고 있어요. [[RERE_PARTNER_GENITIVE]] 표정도 진지해졌네요.", "차분하게 이야기하니 귀 기울이게 되나 봐요!"),
                ("상대의 걱정을 듣고 알맞은 방법을 제안하고 있어요. [[RERE_PARTNER]]도 가만히 이야기를 듣고 있네요.", "서로의 생각을 나누고 있나 봐요!")
            ),
            ["매혹"] = Set(
                ("자연스러운 미소와 말투로 대화를 이어가고 있어요. [[RERE_PARTNER_GENITIVE]] 표정도 좋아보이네요!", "대화 분위기가 부드러워졌어요!"),
                ("상대의 관심사에 맞춰 즐겁게 이야기를 나누고 있어요. [[RERE_PARTNER]]도 편하게 웃고 있네요.", "이야기꽃이 피었나 봐요!")
            ),
            ["역사"] = Set(
                ("기록을 비교하며 사건의 순서를 정리하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 기록을 따라가네요.", "기록을 함께 보니 더 잘 이해되나 봐요!"),
                ("오래된 물건의 특징을 기록과 대조하고 있어요. [[RERE_PARTNER]]도 곁에서 유물을 살펴보고 있네요.", "어떤 이야기가 담겨 있을지 궁금해요!")
            ),
            ["과학"] = Set(
                ("관찰한 현상을 가설과 비교하며 이유를 찾고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 결과를 따라가네요.", "무슨 결과가 나올지 궁금한가 봐요!"),
                ("측정값을 기록하고 예상과 다른 부분을 살펴보고 있어요. [[RERE_PARTNER]]도 옆에서 결과를 지켜보고 있네요.", "작은 차이도 중요한 단서일 수 있어요!")
            ),
            ["감정"] = Set(
                ("작품의 재질과 모양을 살펴보며 가치를 가늠하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 작품을 따라 움직이네요.", "무엇이 특별한지 찾아보나 봐요!"),
                ("그림의 색과 세부를 자세히 살펴보고 있어요. [[RERE_PARTNER]]도 옆에서 작품을 바라보고 있네요.", "같은 그림도 보는 사람마다 다른 점이 보여요!")
            ),
            ["기계수리"] = Set(
                ("작은 도구를 골라 기계를 차근차근 점검하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 손끝을 따라가네요.", "꼼꼼하게 살펴보는 모습이 멋져요!"),
                ("나사가 풀린 곳을 찾아 조심스럽게 조이고 있어요. [[RERE_PARTNER]]도 옆에서 작업을 지켜보고 있네요.", "잘 고쳐지고 있는지 레레도 궁금해요!")
            ),
            ["자동차운전"] = Set(
                ("주변 교통을 살피며 차분하게 운전하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선은 창밖 풍경을 따라가네요.", "안전하게 가는 모습이 든든해요!"),
                ("익숙한 길을 확인하며 부드럽게 차를 몰고 있어요. [[RERE_PARTNER]]도 조수석에서 주변을 바라보고 있네요.", "창밖 풍경도 꽤 근사한가 봐요!")
            ),
            ["수사과학"] = Set(
                ("자료에 남은 흔적을 정리하고 각각의 특징을 비교하고 있어요. [[RERE_PARTNER_GENITIVE]] 시선도 기록을 따라가네요.", "작은 흔적도 놓치지 않고 살펴보나 봐요!"),
                ("관찰한 내용을 순서대로 기록하고 근거를 하나씩 확인하고 있어요. [[RERE_PARTNER]]도 옆에서 메모를 살펴보고 있네요.", "차근차근 확인하는 모습이 믿음직해요!")
            )
        };

    private static readonly Dictionary<string, ObservationActivity[]> BySkill =
        new(StringComparer.OrdinalIgnoreCase)
        {
            ["관찰력"] = Set(
                ("방 안의 장식을 하나씩 살펴보고 있어요.", "작은 것도 잘 발견하네요!"),
                ("창밖의 날씨가 어떻게 바뀌는지 구경하고 있어요.", "오늘은 구름 모양이 재미있어요!"),
                ("테이블 위 물건을 가지런히 정리하며 빠진 게 없는지 보고 있어요.", "정돈된 테이블을 보니 기분이 좋네요!")
            ),
            ["듣기"] = Set(
                ("좋아하는 음악을 들으며 박자를 맞추고 있어요.", "레레도 이 노래 알아요!"),
                ("눈을 감고 밖에서 들려오는 소리에 집중하고 있어요.", "뭐가 들리는걸까요?"),
                ("창문을 살짝 열고 바깥의 빗소리를 듣고 있어요.", "빗소리가 포근하네요!")
            ),
            ["은밀행동"] = Set(
                ("장난스럽게 발소리를 죽이며 숨바꼭질을 하고 있나봐요.", "재미있을 것 같아요. 레레도 찾아볼래요!"),
                ("조용히 방을 지나가며 바닥이 삐걱이는 곳을 피해 보고 있어요.", "레레도 살금살금 따라갈게요!"),
                ("친구를 놀라게 하지 않으려고 살짝 다가가고 있어요.", "[[RERE_CHARACTER_NAME]]은 걸음도 참 조용하네요!")
            ),
            ["심리학"] = Set(
                ("대화 중인 사람의 표정과 말투를 찬찬히 살펴보고 있어요.", "[[RERE_CHARACTER_NAME]]은 마음도 잘 읽는군요!"),
                ("상대가 잠깐 망설인 순간을 떠올리며 무슨 뜻인지 생각하고 있어요.", "레레한테도 알려주면 좋겠어요!"),
                ("말과 행동이 어긋나는 부분이 있는지 조용히 짚어보고 있어요.", "눈치가 정말 빠르네요!")
            ),
            ["자료조사"] = Set(
                ("읽고 싶은 책이나 자료를 찾아 목록으로 정리하고 있어요.", "궁금한 자료가 하나씩 늘어나네요!"),
                ("메모를 주제별로 나누어 보기 좋게 정리하고 있어요.", "[[RERE_CHARACTER_NAME]] 덕분에 찾기 쉬워졌어요!"),
                ("궁금한 내용을 책과 자료에서 찾아 짧게 메모하고 있어요.", "레레도 새로운 걸 하나 더 배운 기분이에요!")
            ),
            ["언어"] = Set(
                ("낯선 문장을 소리 내어 읽으며 발음과 뜻을 맞춰보고 있어요.", "낯선 말도 곧 익숙해질 것 같아요!"),
                ("사전과 메모를 번갈아 보며 문장을 해석하고 있어요.", "[[RERE_CHARACTER_NAME]]은 정말 똑똑하네요!"),
                ("문장 속 반복되는 단어를 찾아 의미를 추측하고 있어요.", "레레도 같이 배워보고 싶어요!")
            ),
            ["예술/공예"] = Set(
                ("작은 소품을 손질하며 모양을 조금씩 다듬고 있어요.", "손끝이 야무지네요!"),
                ("종이에 떠오른 모양을 가볍게 스케치하고 있어요.", "레레도 같이 그림 그리고 싶어요!"),
                ("색과 재료를 골라 자기만의 작품을 만들고 있어요.", "색이 참 예쁘게 어울려요!")
            ),
            ["설득"] = Set(
                ("상대가 납득할 수 있도록 말을 차분히 정리하고 있어요.", "[[RERE_CHARACTER_NAME]]의 말이라면 들어보고 싶어요!"),
                ("서로 원하는 것을 살피며 좋은 방법을 찾고 있어요.", "다 같이 웃을 수 있으면 좋겠어요!"),
                ("상대의 걱정을 먼저 듣고 조심스럽게 의견을 전하고 있어요.", "다정하게 말하는 모습이 멋져요!")
            ),
            ["매혹"] = Set(
                ("상대가 편하게 웃을 수 있도록 분위기를 부드럽게 만들고 있어요.", "[[RERE_CHARACTER_NAME]]은 참 매력적이에요!"),
                ("자연스러운 미소와 말투로 대화를 이어가고 있어요.", "어느새 모두 [[RERE_CHARACTER_NAME]]을 보고 있어요!"),
                ("상대의 관심사에 귀 기울이며 즐겁게 이야기를 나누고 있어요.", "이야기꽃이 활짝 피었네요!")
            ),
            ["위협"] = Set(
                ("거울 앞에서 또렷하고 단호하게 말하는 연습을 하고 있어요.", "자신감 있는 목소리예요!"),
                ("하고 싶은 말을 짧고 분명하게 정리하고 있어요.", "[[RERE_CHARACTER_NAME]]의 말은 귀에 쏙 들어와요!"),
                ("자세를 바르게 하고 당당하게 인사하는 연습을 하고 있어요.", "오늘따라 더 든든해 보여요!")
            ),
            ["말재주"] = Set(
                ("재치 있는 말로 어색해진 분위기를 풀어주고 있어요.", "푸핫, 그 말 재미있어요!"),
                ("상대의 말을 받아 자연스럽게 대화를 이어가고 있어요.", "[[RERE_CHARACTER_NAME]]과 얘기하면 시간이 빨리 가요!"),
                ("누구나 웃을 만한 이야기로 주변의 시선을 모으고 있어요.", "레레도 그 얘기 더 듣고 싶어요!")
            ),
            ["응급처치"] = Set(
                ("구급상자에 필요한 물건이 잘 들어 있는지 확인하고 있어요.", "준비성이 정말 좋아요!"),
                ("반창고와 소독약을 보기 좋게 정리하고 있어요.", "레레 것도 하나 챙겨두면 든든하겠어요!"),
                ("응급처치 안내서를 읽으며 기본 순서를 익히고 있어요.", "[[RERE_CHARACTER_NAME]]이 알고 있으니 든든해요!")
            ),
            ["의학"] = Set(
                ("건강 안내 책자를 읽으며 생활 습관을 살펴보고 있어요.", "건강 챙기는 건 중요하죠!"),
                ("약통의 설명과 날짜를 확인해 가지런히 정리하고 있어요.", "꼼꼼하게 확인했네요!"),
                ("인체에 관한 책을 읽으며 새로 알게 된 내용을 메모하고 있어요.", "[[RERE_CHARACTER_NAME]]의 설명을 들으니 이해가 잘돼요!")
            ),
            ["정신분석"] = Set(
                ("상대가 편안하게 이야기할 수 있도록 조용히 곁을 지키고 있어요.", "[[RERE_CHARACTER_NAME]]은 사람을 편하게 해주는 재주가 있네요!"),
                ("복잡한 감정을 정리할 수 있도록 천천히 질문하고 있어요.", "서두르지 않아도 괜찮아요!"),
                ("상대의 말을 끊지 않고 끝까지 들어주고 있어요.", "다 들어줄게요!")
            ),
            ["생존"] = Set(
                ("외출 가방에 물과 간식이 있는지 확인하고 있어요.", "레레 간식까지 챙겨주다니 다정해요!"),
                ("날씨를 확인하고 산책하기 좋은 길을 고르고 있어요.", "같이 걸으면 좋겠어요!"),
                ("매듭 묶는 법을 연습하며 끈을 가지런히 감고 있어요.", "레레도 매듭 묶어볼래요!")
            ),
            ["추적"] = Set(
                ("산책길에서 전에 보았던 표지판을 기억해 찾아가고 있어요.", "[[RERE_CHARACTER_NAME]]은 길을 잘 기억하네요!"),
                ("동네 지도를 보며 익숙한 길과 새로운 길을 비교하고 있어요.", "다음 산책은 새 길로 가도 재미있겠어요!"),
                ("친구가 추천한 가게까지 가는 길을 메모하고 있어요.", "레레가 옆에서 같이 찾아갈게요!")
            ),
            ["오컬트"] = Set(
                ("별자리와 옛날 전설을 함께 읽어보고 있어요.", "신기한 이야기가 참 많네요!"),
                ("민속 신앙과 풍습에 관한 책을 천천히 읽고 있어요.", "레레도 재미있는 부분을 같이 읽고 싶어요!"),
                ("신비한 이야기에서 마음에 드는 구절을 노트에 적고 있어요.", "레레는 [[RERE_CHARACTER_NAME]]과 책 읽는 시간이 좋아요!")
            ),
            ["역사"] = Set(
                ("오래된 연표를 펼쳐 역사 속 일들의 순서를 정리하고 있어요.", "옛날 이야기는 정말 신기해요!"),
                ("낡은 문장 속 인물과 장소를 다른 기록과 대조하고 있어요.", "레레도 하나씩 기억해둘게요!"),
                ("오래된 물건의 모양을 보고 언제 만들어졌는지 생각하고 있어요.", "[[RERE_CHARACTER_NAME]]은 과거 이야기도 잘 기억하네요!")
            ),
            ["자연"] = Set(
                ("주변의 식물과 작은 생물들을 살펴보고 있어요.", "초록잎이 참 싱그러워요!"),
                ("나뭇잎과 흙의 상태를 살피며 환경을 확인하고 있어요.", "레레도 자연 구경 좋아해요!"),
                ("동물의 발자국과 울음소리를 구분하고 있어요.", "[[RERE_CHARACTER_NAME]]은 동물 친구들과도 잘 지낼 것 같아요!")
            ),
            ["과학"] = Set(
                ("작은 실험 도구를 늘어놓고 결과를 기록하고 있어요.", "무슨 결과일지 생각하는 것도 재미있어요!"),
                ("관찰한 현상을 가설과 비교하며 이유를 찾고 있어요.", "[[RERE_CHARACTER_NAME]]의 설명은 늘 흥미로워요!"),
                ("측정값을 다시 확인하고 예상과 다른 부분을 표시하고 있어요.", "레레가 기록하는 걸 도와줄게요!")
            ),
            ["수사과학"] = Set(
                ("사진과 기록을 대조하며 작은 차이가 있는지 살펴보고 있어요.", "자세히 비교하면 새로운 단서가 보일지도 몰라요!"),
                ("자료에 남은 흔적을 분류하고 각각의 특징을 기록하고 있어요.", "꼼꼼히 기록해두면 나중에 도움이 되겠어요!"),
                ("관찰한 내용을 순서대로 정리하고 근거가 맞는지 확인하고 있어요.", "하나씩 확인하는 모습이 든든해요!")
            ),
            ["감정"] = Set(
                ("마음에 드는 소품의 재질과 모양을 살펴보고 있어요.", "반짝이는 눈으로 보고 있네요!"),
                ("그림이나 장식품의 색과 모양을 자세히 감상하고 있어요.", "[[RERE_CHARACTER_NAME]]은 보는 눈이 있네요!"),
                ("좋아하는 물건을 아껴 쓰려고 상태를 살펴보고 있어요.", "레레라면 그냥 예쁘다고 했을 거예요!")
            ),
            ["회계"] = Set(
                ("이번 달 지출을 적고 용돈을 얼마나 남길지 계산하고 있어요.", "숫자도 [[RERE_CHARACTER_NAME]] 앞에서는 숨을 수 없네요!"),
                ("영수증과 메모를 날짜별로 나누어 정리하고 있어요.", "레레도 꼼꼼히 적어둘게요!"),
                ("장보기 목록을 보며 필요한 물건의 값을 비교하고 있어요.", "와아, 알뜰하게 잘 골랐어요!")
            ),
            ["재력"] = Set(
                ("마음에 드는 물건을 망설임 없이 골라 계산하고 있어요.", "원하는 걸 살 수 있다니 멋져요!"),
                ("필요한 장비를 여유 있게 마련하고 있어요.", "든든하게 준비하는 모습이 근사해요!"),
                ("다 함께 먹을 간식과 음료를 한가득 사 오고 있어요.", "레레 몫도 챙겨주면 정말 기쁠 거예요!")
            ),
            ["법률"] = Set(
                ("생활에 필요한 규칙이나 안내문을 꼼꼼하게 읽고 있어요.", "어려운 말도 척척 읽네요!"),
                ("약속이나 계약에서 중요한 내용을 쉽게 풀어 메모하고 있어요.", "[[RERE_CHARACTER_NAME]]의 설명을 들으니 알 것 같아요!"),
                ("서류를 날짜별로 정리해 필요한 내용을 찾기 쉽게 해두고 있어요.", "레레가 종이를 정리해둘게요!")
            ),
            ["기계수리"] = Set(
                ("자전거와 시계 같은 소지품을 가볍게 점검하고 있어요.", "손재주가 좋네요!"),
                ("작은 도구를 정리하며 쓰기 편한 자리에 놓고 있어요.", "[[RERE_CHARACTER_NAME]]은 기계랑도 친한 것 같아요!"),
                ("나사가 풀린 물건을 살펴보고 제자리에 단단히 조이고 있어요.", "레레가 작은 나사를 맡을게요!")
            ),
            ["전기수리"] = Set(
                ("충전이 필요한 기기와 케이블을 한곳에 모아 정리하고 있어요.", "안전 먼저 확인해요!"),
                ("멀티탭 주변을 살펴보고 선이 엉키지 않게 정돈하고 있어요.", "[[RERE_CHARACTER_NAME]]은 정말 꼼꼼하네요!"),
                ("자주 쓰는 전자기기가 잘 작동하는지 하나씩 확인하고 있어요.", "기기를 정리해 두니 한결 깔끔하네요!")
            ),
            ["자동차운전"] = Set(
                ("차량의 상태를 확인하고 안전한 경로를 살피고 있어요.", "레레는 조수석에 얌전히 앉을게요!"),
                ("익숙한 손놀림으로 차를 천천히 길에 올리고 있어요.", "[[RERE_CHARACTER_NAME]]의 운전은 믿음직스러워요!"),
                ("주변 교통과 날씨를 확인하며 출발할 준비를 하고 있어요.", "레레도 안전띠 꽉 매고 갈게요!")
            ),
            ["수영"] = Set(
                ("물의 흐름을 살피며 천천히 몸을 풀고 있어요.", "레레도 물장구치고 싶어요!"),
                ("호흡을 가다듬고 일정한 속도로 물을 가르고 있어요.", "[[RERE_CHARACTER_NAME]]은 물속에서도 여유롭네요!"),
                ("물가의 깊이와 주변을 확인하며 안전한 곳을 찾고 있어요.", "레레는 얕은 데서 기다릴게요!")
            ),
            ["사격"] = Set(
                ("사격 자세와 안전 수칙을 차분히 되짚어보고 있어요.", "집중한 표정이 멋져요!"),
                ("표적을 맞히는 놀이를 하며 거리를 가늠하고 있어요.", "레레도 한번 해보고 싶어요!"),
                ("호흡을 고르고 다트판의 가운데를 바라보고 있어요.", "[[RERE_CHARACTER_NAME]]이라면 잘 해낼 거예요!")
            ),
            ["회피"] = Set(
                ("몸을 가볍게 풀며 빠르게 피하는 동작을 연습하고 있어요.", "레레가 따라 하다가 빙글 돌았어요!"),
                ("주변을 살피며 어디로 움직일지 미리 생각하고 있어요.", "[[RERE_CHARACTER_NAME]]은 준비성이 좋아요!"),
                ("균형을 잡고 재빠르게 방향을 바꿔보고 있어요.", "레레 눈에는 엄청 빨라 보여요!")
            ),
            ["근접전"] = Set(
                ("자세를 가다듬고 안전하게 동작을 연습하고 있어요.", "레레는 멀리서 응원할게요!"),
                ("주변 공간을 확인하고 움직일 자리를 확보하고 있어요.", "침착한 모습이 든든해요!"),
                ("장비를 살펴보고 필요한 것을 손에 익히고 있어요.", "[[RERE_CHARACTER_NAME]], 다치지 않게 조심해요!")
            ),
            ["고고학"] = Set(
                ("박물관 전시품을 둘러보며 마음에 드는 유물을 살펴보고 있어요.", "엄청 오래된 물건이래요!"),
                ("유물 사진을 모아 시대별로 정리하고 있어요.", "[[RERE_CHARACTER_NAME]]은 과거와 친한가 봐요!"),
                ("작은 수집품을 조심스럽게 닦고 보관함에 정리하고 있어요.", "레레가 부드러운 천을 가져올게요!")
            ),
            ["인류학"] = Set(
                ("사람들의 생활 방식과 관습을 관찰하며 메모하고 있어요.", "레레도 새로운 문화를 배우고 싶어요!"),
                ("낯선 예절을 존중하며 현지 사람들의 이야기를 듣고 있어요.", "[[RERE_CHARACTER_NAME]]은 누구와도 잘 어울리네요!"),
                ("기록과 이야기를 비교해 공동체의 특징을 살피고 있어요.", "이야기 속에 중요한 단서가 있을지도 몰라요!")
            )
        };

    public static ObservationActivity Pick(string skill, string characterName, string? otherCharacterName = null)
    {
        var skillParts = skill.Split('|', 2);
        var baseName = skillParts[0].Trim();
        var activityName = skillParts.Length > 1 &&
            string.Equals(skillParts[1].Trim(), "수사과학", StringComparison.OrdinalIgnoreCase)
                ? "수사과학"
                : baseName;
        if (!string.IsNullOrWhiteSpace(otherCharacterName) &&
            BySkillWithOtherCharacter.TryGetValue(activityName, out var companionActivities) &&
            Random.Shared.Next(3) == 0)
        {
            return Personalize(companionActivities[Random.Shared.Next(companionActivities.Length)], characterName, otherCharacterName);
        }

        if (BySkill.TryGetValue(activityName, out var activities))
            return Personalize(activities[Random.Shared.Next(activities.Length)], characterName);

        var fallback = Set(
            ($"{skill}과 관련된 메모를 정리하며 다음에 해볼 일을 생각하고 있어요.", "[[RERE_CHARACTER_NAME]]은 여러 가지에 관심이 많네요!"),
            ($"잠깐 시간을 내어 {skill}을(를) 연습하고 있어요.", "레레도 옆에서 같이 보고 싶어요!"),
            ($"필요한 도구를 챙겨 {skill}을(를) 준비하고 있어요.", "레레가 필요한 걸 가져다줄게요!")
        );
        return Personalize(fallback[Random.Shared.Next(fallback.Length)], characterName);
    }

    private static ObservationActivity Personalize(ObservationActivity activity, string characterName, string? partnerName = null) =>
        new(
            activity.Action
                .Replace("[[RERE_CHARACTER_NAME]]", characterName, StringComparison.Ordinal)
                .Replace("[[RERE_PARTNER_OBJECT]]", WithParticle(partnerName ?? string.Empty, "를", "을"), StringComparison.Ordinal)
                .Replace("[[RERE_PARTNER_GENITIVE]]", (partnerName ?? string.Empty) + "의", StringComparison.Ordinal),
            activity.RereReaction
                .Replace("[[RERE_CHARACTER_NAME]]", characterName, StringComparison.Ordinal)
                .Replace("[[RERE_PARTNER_NAME]]", partnerName ?? string.Empty, StringComparison.Ordinal));

    public static string TopicParticle(string name)
    {
        var nameWithParticle = WithParticle(name, "는", "은");
        return nameWithParticle[name.Length..];
    }

    private static string WithParticle(string name, string vowelParticle, string consonantParticle)
    {
        if (string.IsNullOrWhiteSpace(name))
            return name + vowelParticle;

        var last = name.TrimEnd()[^1];
        if (last is >= '\uAC00' and <= '\uD7A3')
            return name + ((last - '\uAC00') % 28 == 0 ? vowelParticle : consonantParticle);

        // Sheet character names are usually Korean; use the vowel form for Latin names.
        return name + vowelParticle;
    }

    private static ObservationActivity[] Set(params (string Action, string Reaction)[] items) =>
        items.Select(item => new ObservationActivity(item.Action, item.Reaction)).ToArray();
}
