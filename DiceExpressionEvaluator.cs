using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

public sealed class DiceExpressionResult
{
    public decimal Total { get; }
    public IReadOnlyList<string> Rolls { get; }

    public DiceExpressionResult(decimal total, IReadOnlyList<string> rolls)
    {
        Total = total;
        Rolls = rolls;
    }
}

public static class DiceExpressionEvaluator
{
    public static DiceExpressionResult Evaluate(string expression)
    {
        if (string.IsNullOrWhiteSpace(expression) || expression.Length > 100)
            throw new FormatException("식은 1~100자여야 해요.");

        var parser = new Parser(expression);
        var total = parser.Parse();
        return new DiceExpressionResult(total, parser.Rolls);
    }

    private sealed class Parser
    {
        private readonly string _text;
        private int _position;
        private int _totalDice;
        public List<string> Rolls { get; } = new();

        public Parser(string text) => _text = text;

        public decimal Parse()
        {
            var value = ParseExpression();
            SkipSpaces();
            if (_position != _text.Length)
                throw new FormatException($"'{_text[_position]}' 위치를 확인해 주세요.");
            return value;
        }

        private decimal ParseExpression()
        {
            var value = ParseTerm();
            while (true)
            {
                SkipSpaces();
                if (Take('+')) value += ParseTerm();
                else if (Take('-')) value -= ParseTerm();
                else return value;
                EnsureFinite(value);
            }
        }

        private decimal ParseTerm()
        {
            var value = ParseUnary();
            while (true)
            {
                SkipSpaces();
                if (Take('*')) value *= ParseUnary();
                else if (Take('/'))
                {
                    var divisor = ParseUnary();
                    if (divisor == 0)
                        throw new InvalidOperationException("0으로 나눌 수 없어요.");
                    value /= divisor;
                }
                else return value;
                EnsureFinite(value);
            }
        }

        private decimal ParseUnary()
        {
            SkipSpaces();
            if (Take('+')) return ParseUnary();
            if (Take('-')) return -ParseUnary();
            return ParsePrimary();
        }

        private decimal ParsePrimary()
        {
            SkipSpaces();
            if (Take('('))
            {
                var value = ParseExpression();
                SkipSpaces();
                if (!Take(')')) throw new FormatException("괄호가 닫히지 않았어요.");
                return value;
            }

            var number = ReadInteger();
            SkipSpaces();
            if (Take('d') || Take('D'))
                return RollDice(number, ReadInteger());

            return number;
        }

        private decimal RollDice(decimal countValue, decimal sidesValue)
        {
            if (countValue != decimal.Truncate(countValue) || countValue < 1 || countValue > 100)
                throw new InvalidOperationException("한 번에 같은 주사위는 1~100개까지 굴릴 수 있어요.");
            if (sidesValue != decimal.Truncate(sidesValue) || sidesValue < 1 || sidesValue > 1000000)
                throw new InvalidOperationException("주사위 눈 수는 1~1,000,000 사이의 정수여야 해요.");

            var count = (int)countValue;
            var sides = (int)sidesValue;
            _totalDice += count;
            if (_totalDice > 200)
                throw new InvalidOperationException("한 식에서 굴릴 수 있는 주사위는 총 200개까지예요.");

            var values = new int[count];
            for (var i = 0; i < count; i++)
                values[i] = Random.Shared.Next(1, sides + 1);

            Rolls.Add($"{count}d{sides} [{string.Join(", ", values)}]");
            return values.Sum(value => (decimal)value);
        }

        private decimal ReadInteger()
        {
            SkipSpaces();
            var start = _position;
            while (_position < _text.Length && char.IsDigit(_text[_position])) _position++;
            if (start == _position)
                throw new FormatException($"{_position + 1}번째 위치에 숫자나 주사위 식이 필요해요.");
            if (!decimal.TryParse(_text[start.._position], NumberStyles.None, CultureInfo.InvariantCulture, out var value))
                throw new FormatException("숫자가 너무 커요.");
            return value;
        }

        private bool Take(char expected)
        {
            if (_position >= _text.Length || _text[_position] != expected) return false;
            _position++;
            return true;
        }

        private void SkipSpaces()
        {
            while (_position < _text.Length && char.IsWhiteSpace(_text[_position])) _position++;
        }

        private static void EnsureFinite(decimal value)
        {
            if (value > 1000000000000m || value < -1000000000000m)
                throw new InvalidOperationException("계산 결과가 너무 커요.");
        }
    }
}
