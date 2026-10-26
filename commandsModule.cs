using System.Threading.Tasks;
using Discord;
using Discord.Interactions;
using Discord.WebSocket;
using System;
using System.Linq;
using Microsoft.VisualBasic;
using System.Collections.Generic;

public class CommandsModule : InteractionModuleBase<SocketInteractionContext>
{
    private readonly SheetRegistry _sheetRegistry;
    private static readonly Dictionary<string, int> SkillBaseValues = new(StringComparer.OrdinalIgnoreCase)
    {
        ["관찰력"] = 25, ["듣기"] = 20, ["은밀행동"] = 20, ["심리학"] = 10,
        ["자료조사"] = 20, ["언어"] = 1, ["예술/공예"] = 5, ["설득"] = 10,
        ["매혹"] = 15, ["위협"] = 15, ["말재주"] = 5, ["응급처치"] = 30,
        ["의학"] = 1, ["정신분석"] = 1, ["생존"] = 10, ["추적"] = 10,
        ["오컬트"] = 5, ["역사"] = 5, ["자연"] = 10, ["과학"] = 1,
        ["수사과학"] = 1, ["감정"] = 5, ["회계"] = 5, ["법률"] = 5,
        ["기계수리"] = 10, ["전기수리"] = 10, ["자동차운전"] = 20,
        ["오르기"] = 20, ["수영"] = 20, ["사격"] = 20, ["회피"] = 0,
        ["근접전"] = 25, ["고고학"] = 1, ["인류학"] = 1,
        ["변장"] = 5, ["자물쇠따기"] = 1, ["조종"] = 1, ["손재주"] = 10,
        ["항법"] = 10, ["도약"] = 20, ["승마"] = 5, ["투척"] = 20,
        ["신용"] = 0, ["크툴루신화"] = 0, ["폭파"] = 1
    };

    public CommandsModule(SheetRegistry sheetRegistry)
    {
        _sheetRegistry = sheetRegistry;
    }

    [SlashCommand("관찰", "캐릭터들이 무엇을 하고 있는지 살펴보고 올게요!")]
    public async Task Observe([Autocomplete(typeof(CharacterAutocompleteHandler))] string 캐릭터)
    {
        IReadOnlyDictionary<string, int>? 기능값들;
        IReadOnlyDictionary<string, int>? 투자값들;
        try
        {
            기능값들 = await _sheetRegistry.GetSkillValuesAsync(캐릭터);
            투자값들 = await _sheetRegistry.GetSkillInvestmentValuesAsync(캐릭터);
        }
        catch (HttpRequestException)
        {
            await RespondAsync("Google 시트에 연결하지 못했어요. 잠시 후 다시 시도해 주세요!", ephemeral: true);
            return;
        }
        catch (InvalidOperationException ex)
        {
            await RespondAsync(ex.Message, ephemeral: true);
            return;
        }

        if (기능값들 is null || 기능값들.Count == 0)
        {
            await RespondAsync("시트에서 캐릭터의 기능치를 찾지 못했어요. 캐릭터 등록과 시트 내용을 확인해 주세요!", ephemeral: true);
            return;
        }

        var characteristicNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "근력", "민첩", "정신", "건강", "외모", "교육", "크기", "지능", "행운", "이성"
        };
        var candidates = 기능값들
            .Where(pair => !characteristicNames.Contains(pair.Key.Split('|', 2)[0].Trim()))
            .Select(pair =>
            {
                var skillParts = pair.Key.Split('|', 2);
                var baseSkillName = skillParts[0].Trim();
                var specialization = skillParts.Length > 1 ? skillParts[1].Trim() : string.Empty;
                var lookupName = specialization.Equals("수사과학", StringComparison.OrdinalIgnoreCase)
                    ? specialization
                    : baseSkillName;
                var defaultValue = SkillBaseValues.TryGetValue(lookupName, out var knownDefault)
                    ? knownDefault
                    : 20;
                if (lookupName.Equals("회피", StringComparison.OrdinalIgnoreCase) &&
                    기능값들.TryGetValue("민첩", out var dexterity))
                    defaultValue = dexterity / 2;

                return (Skill: pair.Key, Weight: Math.Max(1, pair.Value - defaultValue + 1));
            })
            .ToArray();
        if (candidates.Length == 0)
        {
            await RespondAsync("이 캐릭터의 기능치를 찾지 못했어요. 시트에 기능치가 있는지 확인해 주세요!", ephemeral: true);
            return;
        }
        var separator = 캐릭터.IndexOf('|');
        var characterName = separator >= 0 ? 캐릭터[(separator + 1)..].Trim() : 캐릭터;
        if (Random.Shared.Next(100) < 30)
        {
            var restActivities = new (string Action, string Reaction)[]
            {
                ("잠시 자리에 앉아 쉬고 있었어요!", "잠깐 쉬어가는 것도 좋죠!"),
                ("따뜻한 차를 마시며 여유를 즐기고 있었어요!", "따뜻한 차 한 잔은 마음까지 편안하게 해줘요!"),
                ("짧게 낮잠을 자고 있었어요!", "푹 쉬고 나면 한결 개운할 거예요!"),
                ("간단한 간식을 먹으며 쉬고 있었어요!", "맛있는 간식은 기운을 북돋아 줘요!"),
                ("물을 마시며 잠시 숨을 고르고 있었어요!", "수분 보충도 잊지 않았네요!"),
                ("창가에 앉아 바깥 풍경을 바라보고 있었어요!", "잠시 멍하니 바라보는 시간도 좋네요!"),
                ("음악을 들으며 쉬고 있었어요!", "무슨 음악을 듣고 있는 걸까요?"),
                ("가볍게 스트레칭하며 몸을 풀고 있었어요!", "와아, 레레도 같이 스트레칭해보고 싶어요!"),
                ("읽던 책을 펼쳐놓고 느긋하게 읽고 있었어요!", "여유로운 독서 시간, 참 좋네요!"),
                ("담요를 덮고 포근하게 쉬고 있었어요!", "따뜻하고 편안해 보여요!"),
                ("창문을 열어 산뜻한 바람을 쐬고 있었어요!", "바람이 살랑살랑 불어서 기분이 좋아 보여요!"),
                ("따뜻한 우유를 마시며 잠시 쉬고 있었어요!", "마음이 몽글몽글해지는 시간이네요!"),
                ("간단히 식사를 하며 에너지를 채우고 있었어요!", "레레는 모르지만, 든든하게 챙겨 먹으면 힘이 난대요!"),
                ("햇볕이 드는 곳에 앉아 잠깐 눈을 감고 있었어요!", "햇살이 포근하게 감싸주는 것 같아요!"),
                ("좋아하는 노래를 작게 흥얼거리며 쉬고 있었어요!", "좋아하는 노래인가 봐요!"),
                ("주변을 가볍게 정리하고 있었어요!", "정돈된 모습을 보니 마음도 편안해져요!"),
                ("주변을 천천히 산책하고 있었어요!", "걷다 보면 기분이 조금 가벼워질 거예요!")
            };
            var restAction = string.Empty;
            var restReaction = string.Empty;
            var restOtherCharacterNames = new List<string>();
            if (separator > 0)
            {
                try
                {
                    var sameSheetCharacters = await _sheetRegistry.GetCharacterTabChoicesAsync(캐릭터[..separator]);
                    restOtherCharacterNames = sameSheetCharacters
                        .Select(choice => choice.Value[(choice.Value.IndexOf('|') + 1)..])
                        .Where(name => !string.Equals(name, characterName, StringComparison.OrdinalIgnoreCase))
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .ToList();
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Observation rest character lookup failed ({ex.GetType().Name}).");
                }
            }

            if (restOtherCharacterNames.Count > 0 && Random.Shared.Next(3) == 0)
            {
                var restInteractions = new (string Action, string Reaction)[]
                {
                    ("[[RERE_PARTNER_COMITATIVE]] 나란히 앉아 차를 마시며 쉬고 있었어요!", "차 향이 은은하게 퍼지네요!"),
                    ("[[RERE_PARTNER_DATIVE]] 간식을 하나 건네고 있었어요!", "간식을 나눠주다니, 상냥해요!"),
                    ("[[RERE_PARTNER_COMITATIVE]] 창밖 풍경을 바라보며 쉬고 있었어요!", "바깥 풍경이 평화로워 보여요!"),
                    ("[[RERE_PARTNER_COMITATIVE]] 조용히 음악을 들으며 쉬고 있었어요!", "잔잔한 곡이라 쉬는 분위기와 잘 어울려요!"),
                    ("[[RERE_PARTNER_GENITIVE]] 옆에서 각자 책을 읽으며 쉬고 있었어요!", "책장이 넘어가는 소리만 들려서 차분하네요!"),
                    ("[[RERE_PARTNER_COMITATIVE]] 가볍게 스트레칭하며 몸을 풀고 있었어요!", "몸을 풀어주면 한결 개운하겠어요!")
                };
                var partnerName = restOtherCharacterNames[Random.Shared.Next(restOtherCharacterNames.Count)];
                var selected = restInteractions[Random.Shared.Next(restInteractions.Length)];
                var interaction = ObservationActivities.Personalize(
                    new ObservationActivity(selected.Action, selected.Reaction), characterName, partnerName);
                restAction = interaction.Action;
                restReaction = interaction.RereReaction;
            }
            else
            {
                var rest = restActivities[Random.Shared.Next(restActivities.Length)];
                restAction = rest.Action;
                restReaction = rest.Reaction;
            }

            await RespondAsync(
                $"레레가 살짝 보고 왔는데, **{characterName}**{ObservationActivities.TopicParticle(characterName)} {restAction} {restReaction}",
                ephemeral: false);
            return;
        }

        var occupation = await _sheetRegistry.GetOccupationAsync(캐릭터);
        if (!string.IsNullOrWhiteSpace(occupation) && Random.Shared.Next(10) == 0)
        {
            var occupationActivities = new[]
            {
                $"{occupation} 일을 하고 있었어요! 집중하는 모습이 눈에 들어오네요!",
                $"{occupation} 일을 시작하기 전에 오늘 일정을 확인하고 있었어요! 차근차근 준비하는 모습이 보기 좋아요!"
            };
            var occupationActivity = occupationActivities[Random.Shared.Next(occupationActivities.Length)];
            await RespondAsync(
                $"레레가 살짝 보고 왔는데, **{characterName}**{ObservationActivities.TopicParticle(characterName)} {occupationActivity}",
                ephemeral: false);
            return;
        }

        string selectedSkill;
        if (투자값들 is not null)
        {
            var investedCandidates = candidates
                .Select(candidate => (candidate.Skill, Weight: 투자값들.TryGetValue(candidate.Skill, out var points) ? points : 0))
                .Where(candidate => candidate.Weight > 0)
                .ToArray();
            var uninvestedCandidates = candidates
                .Where(candidate => !투자값들.TryGetValue(candidate.Skill, out var points) || points <= 0)
                .Select(candidate => candidate.Skill)
                .ToArray();

            if (investedCandidates.Length > 0)
            {
                // Keep a small chance for default skills while preventing their count from dominating.
                selectedSkill = uninvestedCandidates.Length == 0 || Random.Shared.Next(100) < 95
                    ? PickWeightedSkill(investedCandidates)
                    : uninvestedCandidates[Random.Shared.Next(uninvestedCandidates.Length)];
            }
            else
                selectedSkill = candidates[Random.Shared.Next(candidates.Length)].Skill;
        }
        else
            selectedSkill = PickWeightedSkill(candidates.Select(candidate => (candidate.Skill, candidate.Weight)).ToArray());

        var otherCharacterNames = new List<string>();
        if (separator > 0)
        {
            try
            {
                var sameSheetCharacters = await _sheetRegistry.GetCharacterTabChoicesAsync(캐릭터[..separator]);
                otherCharacterNames = sameSheetCharacters
                    .Select(choice => choice.Value[(choice.Value.IndexOf('|') + 1)..])
                    .Where(name => !string.Equals(name, characterName, StringComparison.OrdinalIgnoreCase))
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .ToList();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Observation character lookup failed ({ex.GetType().Name}).");
            }
        }

        var otherCharacterName = otherCharacterNames.Count > 0
            ? otherCharacterNames[Random.Shared.Next(otherCharacterNames.Count)]
            : null;
        var activity = ObservationActivities.Pick(selectedSkill, characterName, otherCharacterName);
        var activityDescription = activity.Action.Replace("있어요.", "있었어요!", StringComparison.Ordinal);
        await RespondAsync(
            $"레레가 살짝 보고 왔는데, **{characterName}**{ObservationActivities.TopicParticle(characterName)} {activityDescription} {activity.RereReaction}",
            ephemeral: false);
    }

    private static string PickWeightedSkill((string Skill, int Weight)[] candidates)
    {
        var totalWeight = candidates.Sum(candidate => candidate.Weight);
        var ticket = Random.Shared.Next(1, totalWeight + 1);
        foreach (var candidate in candidates)
        {
            ticket -= candidate.Weight;
            if (ticket <= 0)
                return candidate.Skill;
        }
        return candidates[^1].Skill;
    }

    [SlashCommand("응원", "레레가 응원할게요!")]
    public async Task Cheer()
    {
        string[] messages =
        {
            "파이팅~! 레레가 힘을 보탤게요!",
            "괜찮아요, 분명 잘할 수 있어요! 레레가 응원할게요!",
            "레레의 응원을 보낼게요! 힘내요~!",
            "너무 걱정하지 말아요. 레레가 곁에서 응원하고 있어요!",
            "작은 한 걸음도 멋진 시작이에요! 파이팅이에요!",
            "힘이 필요할 땐 레레를 불러주세요! 언제나 응원할게요!",
            "오늘도 충분히 잘하고 있어요! 레레가 힘을 보탤게요!",
            "아자~! 레레의 응원으로 기운이 났으면 좋겠어요!"
        };

        await RespondAsync(messages[Random.Shared.Next(messages.Length)], ephemeral: false);
    }

    [SlashCommand("선택", "쉼표로 나눠서 말해주면 하나를 골라줄게요!")]
    public async Task Choose(string 항목들)
    {
        var choices = 항목들
            .Split(new[] { ',', '，', '、' }, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
            .Select(choice => choice.Trim())
            .Where(choice => !string.IsNullOrWhiteSpace(choice))
            .ToArray();

        if (choices.Length < 2)
        {
            await RespondAsync("쉼표로 나눠서 선택지를 두 개 이상 입력해 주세요! 예: `빨강, 파랑, 초록`", ephemeral: true);
            return;
        }

        var selected = choices[Random.Shared.Next(choices.Length)];
        await RespondAsync($"레레가 고른 건,  **[{selected}]** 예요!", ephemeral: false);
    }

    [SlashCommand("기능판정", "캐릭터와 기능을 골라 바로 판정해요!")]
    public async Task Dice(
        [Autocomplete(typeof(CharacterAutocompleteHandler))] string 캐릭터,
        [Autocomplete(typeof(SkillAutocompleteHandler))] string 기능,
        [Autocomplete(typeof(RollModeAutocompleteHandler))]
        [Summary("패널티_보너스", "패널티 또는 보너스를 선택해요. 비워두면 일반 굴림이에요.")]
        string? 패널티_보너스 = null)
    {
        var isValidRollMode = string.IsNullOrWhiteSpace(패널티_보너스) || 패널티_보너스 is
            "패널티+1" or "패널티+2" or "보너스+1" or "보너스+2";
        if (!isValidRollMode)
        {
            await RespondAsync("패널티/보너스 값이 올바르지 않아요. 선택 목록에서 `패널티 +1`, `패널티 +2`, `보너스 +1`, `보너스 +2` 중 하나를 골라 주세요. 비워두면 일반 굴림이에요!", ephemeral: true);
            return;
        }

        int? 기능값;
        try
        {
            기능값 = await _sheetRegistry.GetSkillValueAsync(캐릭터, 기능);
        }
        catch (HttpRequestException)
        {
            await RespondAsync("Google 시트에 연결하지 못했어요. 인터넷 연결과 API 키 설정을 확인해 주세요!", ephemeral: false);
            return;
        }
        catch (InvalidOperationException ex)
        {
            await RespondAsync(ex.Message, ephemeral: false);
            return;
        }

        if (기능값 is null)
        {
            await RespondAsync("캐릭터나 기능값을 시트에서 찾지 못했어요. `/캐릭터등록`에서 캐릭터를 등록하고 기능 이름을 확인해 주세요!", ephemeral: false);
            return;
        }

        var 캐릭터이름 = 캐릭터[(캐릭터.IndexOf('|') + 1)..];
        var 보정표시 = 패널티_보너스 switch
        {
            "패널티+1" => " — 패널티 +1",
            "패널티+2" => " — 패널티 +2",
            "보너스+1" => " — 보너스 +1",
            "보너스+2" => " — 보너스 +2",
            _ => string.Empty
        };
        var rollCount = 패널티_보너스 switch
        {
            "패널티+1" or "보너스+1" => 2,
            "패널티+2" or "보너스+2" => 3,
            _ => 1
        };
        var rolls = Enumerable.Range(0, rollCount)
            .Select(_ => Random.Shared.Next(1, 101))
            .ToArray();
        var isPenalty = 패널티_보너스 is "패널티+1" or "패널티+2";
        var isBonus = 패널티_보너스 is "보너스+1" or "보너스+2";
        var randomNumber = isPenalty ? rolls.Max() : isBonus ? rolls.Min() : rolls[0];
        var isSanityCheck = string.Equals(기능, "이성", StringComparison.OrdinalIgnoreCase);
        var 판정 = isSanityCheck
            ? randomNumber <= 기능값.Value ? "성공" : "실패"
            : randomNumber == 1
                ? "대성공"
                : 기능값.Value < 50 && randomNumber >= 95 || 기능값.Value >= 50 && randomNumber == 100
                    ? "대실패"
                    : randomNumber <= 기능값.Value / 5
                        ? "극단적 성공"
                        : randomNumber <= 기능값.Value / 2
                            ? "어려운 성공"
                            : randomNumber <= 기능값.Value
                                ? "보통 성공"
                                : "실패";

        var succeeded = 판정 != "실패" && 판정 != "대실패";
        var ending = succeeded ? "이에요!" : "예요!";
        var rollDisplay = $"[ {string.Join(", ", rolls)} ]";
        var appliedRollDescription = isPenalty
            ? $"이 나왔으므로 더 높은 값인 [ {randomNumber} ]을 적용해서 "
            : isBonus
                ? $"이 나왔으므로 더 낮은 값인 [ {randomNumber} ]을 적용해서 "
                : "이 나왔으므로 ";
        string? emote = null;
        try
        {
            var emoteName = await _sheetRegistry.GetCharacterEmoteNameAsync(캐릭터, succeeded);
            if (!string.IsNullOrWhiteSpace(emoteName))
            {
                emote = Context.Guild.Emotes
                    .FirstOrDefault(candidate => string.Equals(candidate.Name, emoteName, StringComparison.OrdinalIgnoreCase))
                    ?.ToString();
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Character emote lookup failed ({ex.GetType().Name}).");
        }

        var emoteSuffix = string.IsNullOrWhiteSpace(emote) ? string.Empty : $" {emote}";
        await RespondAsync($"**{캐릭터이름} — {기능} ({기능값}){보정표시}**\n> {rollDisplay}{appliedRollDescription}***{판정}*** {ending}{emoteSuffix}", ephemeral: false);

    }

    [SlashCommand("임의판정", "기능치를 입력해 시트 없이 판정해요!")]
    public async Task ArbitraryCheck(int 기능치)
    {
        if (기능치 is < 1 or > 100)
        {
            await RespondAsync("기능치는 1부터 100 사이의 숫자로 입력해 주세요!", ephemeral: true);
            return;
        }

        var roll = Random.Shared.Next(1, 101);
        var 판정 = roll == 1
            ? "대성공"
            : 기능치 < 50 && roll >= 95 || 기능치 >= 50 && roll == 100
                ? "대실패"
                : roll <= 기능치 / 5
                    ? "극단적 성공"
                    : roll <= 기능치 / 2
                        ? "어려운 성공"
                        : roll <= 기능치
                            ? "보통 성공"
                            : "실패";
        var ending = 판정 is "실패" or "대실패" ? "예요!" : "이에요!";
        await RespondAsync($"**임의 판정 ({기능치})**\n> 1d100 [{roll}]이 나와서 ***{판정}*** {ending}", ephemeral: false);
    }

    [SlashCommand("주사위", "주사위를 굴려요! 예: 1d100+2d6")]
    public Task RollDice(string 굴리기) => RollDiceAsync(굴리기, ephemeral: false);

    [SlashCommand("비밀주사위", "주사위 결과를 나에게만 보여줘요! 예: 1d100+2d6")]
    public Task SecretRollDice(string 굴리기) => RollDiceAsync(굴리기, ephemeral: true);

    private async Task RollDiceAsync(string 굴리기, bool ephemeral)
    {
        await DeferAsync(ephemeral: ephemeral);
        try
        {
            var result = DiceExpressionEvaluator.Evaluate(굴리기);
            var diceResults = result.Rolls.Count == 0
                ? $"계산값 [{result.Total:0.##}]"
                : string.Join(" + ", result.Rolls);
            var secretPrefix = ephemeral ? "이건 비밀인데...\n" : string.Empty;
            await ModifyOriginalResponseAsync(message => message.Content =
                $"{secretPrefix}굴린 주사위: `{굴리기}`\n주사위 값이 {diceResults}가 나와서, [{result.Total:0.##}]예요!");
        }
        catch (FormatException ex)
        {
            await ModifyOriginalResponseAsync(message => message.Content = $"주사위 식을 읽지 못했어요. `1d100+2d6`처럼 입력해 주세요!\n{ex.Message}");
        }
        catch (InvalidOperationException ex)
        {
            await ModifyOriginalResponseAsync(message => message.Content = ex.Message);
        }
    }

    [SlashCommand("운세", "오늘의 운세")]
    public async Task fortune()
    {
        string[] fortunes =
        {
        "레레가 봤을 때, 오늘의 당신은 행복할 거예요!",
        "레레가 봤을 때, 행운이 넘치는 날이 될 거예요!",
        "레레가 봤을 때, 당신은 오늘 아주 멋질 거예요!",
        "레레가 봤을 때, 오늘은 친구의 도움이 있을 거예요!",
        "레레가 봤을 때, 좋은 일이 생길 것 같아요!",
        "레레가 봤을 때, 오늘은 상냥하게 말하면 좋을 것 같아요!",
        "레레가 봤을 때, 사랑이 넘치는 날이 될 거예요!",
        "레레가 봤을 때, 레레를 칭찬하면 좋은 일이 있을 것 같아요! 헤헤.",
        "레레가 봤을 때, 조언이 전혀 필요하지 않을 것 같은걸요!",
        "레레가 봤을 때, 행운의 부적과 함께라면 뭐든 할 수 있어요!",
        "레레가 봤을 때, 주변을 살피는 게 좋을 것 같아요!",
        "레레가 봤을 때, 오늘은 작은 일도 차근차근 해내는 날이 될 거예요!",
        "레레가 봤을 때, 잠깐 쉬어가면 더 좋은 생각이 떠오를 거예요!",
        "레레가 봤을 때, 우연히 발견한 것이 기분 좋은 힌트가 될 것 같아요!",
        "레레가 봤을 때, 오늘 건넨 친절이 따뜻한 마음으로 돌아올 거예요!",
        "레레가 봤을 때, 망설이던 일을 시작하기에 괜찮은 날이에요!",
        "레레가 봤을 때, 좋아하는 음악이 오늘의 기분을 바꿔줄 거예요!",
        "레레가 봤을 때, 맛있는 걸 먹으면 좋은 기운이 찾아올 거예요!",
        "레레가 봤을 때, 오늘은 평소보다 조금 느긋해도 괜찮아요!",
        "레레가 봤을 때, 누군가의 반가운 소식을 듣게 될지도 몰라요!",
        "레레가 봤을 때, 작은 용기를 내면 생각보다 잘 풀릴 거예요!",
        "레레가 봤을 때, 오늘의 실수는 내일을 위한 좋은 경험이 될 거예요!",
        "레레가 봤을 때, 당신 곁에 있는 소중한 것들을 발견하는 날이에요!"
    };

        Random random = new Random();
        int index = random.Next(fortunes.Length);  // 배열 크기만큼 랜덤 값 생성

        await RespondAsync(fortunes[index]);
    }

    [SlashCommand("캐릭터등록", "시트와 캐릭터를 고르고 최대 5명까지 등록해요!")]
    [RequireContext(ContextType.Guild)]
    public async Task RegisterCharacters(
        [Autocomplete(typeof(SheetAutocompleteHandler))] string 시트,
        [Autocomplete(typeof(RegistrationCharacterAutocompleteHandler))] string 캐릭터1,
        [Autocomplete(typeof(RegistrationCharacterAutocompleteHandler))] string? 캐릭터2 = null,
        [Autocomplete(typeof(RegistrationCharacterAutocompleteHandler))] string? 캐릭터3 = null,
        [Autocomplete(typeof(RegistrationCharacterAutocompleteHandler))] string? 캐릭터4 = null,
        [Autocomplete(typeof(RegistrationCharacterAutocompleteHandler))] string? 캐릭터5 = null)
    {
        try
        {
            var spreadsheet = (await _sheetRegistry.GetAvailableSheetsAsync())
                .FirstOrDefault(sheet => sheet.SpreadsheetId == 시트);
            if (spreadsheet is null)
            {
                await RespondAsync("시트를 목록에서 골라 주세요.", ephemeral: true);
                return;
            }

            var validCharacterValues = spreadsheet.Tabs
                .Select(tab => $"{spreadsheet.SpreadsheetId}|{tab}")
                .ToHashSet(StringComparer.Ordinal);
            var selected = new[] { 캐릭터1, 캐릭터2, 캐릭터3, 캐릭터4, 캐릭터5 }
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value!)
                .Distinct(StringComparer.Ordinal)
                .ToArray();
            if (selected.Length == 0 || selected.Any(value => !validCharacterValues.Contains(value)))
            {
                await RespondAsync("캐릭터는 선택한 시트의 탭 목록에서 골라 주세요. 첫 번째 캐릭터는 꼭 선택해야 해요.", ephemeral: true);
                return;
            }

            await _sheetRegistry.AddUserCharacterSelectionsForSheetAsync(Context.User.Id, spreadsheet.SpreadsheetId, selected);
            var characterNames = selected.Select(value => value[(value.IndexOf('|') + 1)..]);
            await RespondAsync($"**{spreadsheet.Title}**에서 {string.Join(", ", characterNames)} 캐릭터를 등록했어요!", ephemeral: true);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"Character registration failed ({ex.GetType().Name}).");
            await RespondAsync("캐릭터를 등록하지 못했어요. 잠시 후 다시 시도해 주세요!", ephemeral: true);
        }
    }

    [SlashCommand("캐릭터목록", "내가 등록한 캐릭터를 보여드려요!")]
    [RequireContext(ContextType.Guild)]
    public async Task ListCharacters()
    {
        var selected = await _sheetRegistry.GetUserCharacterSelectionAsync(Context.User.Id);
        if (selected is null || selected.Count == 0)
        {
            await RespondAsync("아직 등록한 캐릭터가 없어요! `/캐릭터등록`에서 시트와 캐릭터를 골라 주세요.", ephemeral: true);
            return;
        }

        var selectedSet = selected.ToHashSet(StringComparer.Ordinal);
        var spreadsheets = await _sheetRegistry.GetAvailableSheetsAsync();
        var lines = spreadsheets.Select((sheet, index) =>
        {
            var characters = sheet.Tabs
                .Where(tab => selectedSet.Contains($"{sheet.SpreadsheetId}|{tab}"))
                .ToArray();
            return characters.Length == 0
                ? null
                : $"**{sheet.Title}**\n{string.Join(", ", characters)}";
        }).Where(line => line is not null);
        var message = string.Join("\n\n", lines);
        if (string.IsNullOrWhiteSpace(message))
        {
            await RespondAsync("등록된 캐릭터를 시트에서 찾지 못했어요. `/캐릭터등록`을 다시 진행해 주세요!", ephemeral: true);
            return;
        }
        if (message.Length > 1900)
            message = message[..1900] + "…";
        await RespondAsync(message, ephemeral: true);
    }

    [SlashCommand("캐릭터리셋", "내가 기억해 둔 캐릭터 목록을 비워요!")]
    [RequireContext(ContextType.Guild)]
    public async Task ResetCharacters()
    {
        var cleared = await _sheetRegistry.ClearUserCharacterSelectionsAsync(Context.User.Id);
        var message = cleared
            ? "기억하고 있던 캐릭터 목록을 비웠어요. 다시 사용하려면 `/캐릭터등록`으로 등록해 주세요!"
            : "비울 캐릭터 목록이 없어요.";
        await RespondAsync(message, ephemeral: true);
    }



}



