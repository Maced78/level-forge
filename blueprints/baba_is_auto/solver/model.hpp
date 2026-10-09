// model.hpp - a compact state-transition model of baba-is-auto, written by
// Agent 1 from the engine source (Sources/baba-is-auto/Games/Game.cpp).
//
// It covers exactly the subset listed in IsModelEligible(): ordinary nouns,
// IS, and the properties YOU / STOP / PUSH / WIN / SINK / DEFEAT, plus noun
// transformations (X IS Y).  It exists only because the real engine explores
// ~2,000 states/s; the model explores ~100,000 states/s, which makes
// exhaustive proofs practical.
//
// Trust is NOT assumed:
//   * every solution the model finds is replayed in the real engine before a
//     level is called solvable;
//   * `babasolve --difftest` walks the model and the real engine side by side
//     and compares the complete board after every move;
//   * levels outside the subset are searched with the real engine instead.
//
// Each function below names the engine function it mirrors.
#ifndef FORGE_BABA_MODEL_HPP
#define FORGE_BABA_MODEL_HPP

#include <baba-is-auto/Games/Game.hpp>

#include <algorithm>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace forge
{
using baba_is_auto::Direction;
using baba_is_auto::ObjectType;

enum : std::uint8_t
{
    P_YOU = 1,
    P_STOP = 2,
    P_PUSH = 4,
    P_WIN = 8,
    P_SINK = 16,
    P_DEFEAT = 32
};

inline std::uint8_t PropBit(ObjectType t)
{
    switch (t)
    {
        case ObjectType::YOU: return P_YOU;
        case ObjectType::STOP: return P_STOP;
        case ObjectType::PUSH: return P_PUSH;
        case ObjectType::WIN: return P_WIN;
        case ObjectType::SINK: return P_SINK;
        case ObjectType::DEFEAT: return P_DEFEAT;
        default: return 0;
    }
}

// Words the model gives the same meaning as the engine.
inline bool IsModelWord(ObjectType t)
{
    using namespace baba_is_auto;
    if (IsIconType(t)) return true;
    if (IsLockedType(t)) return false;
    if (IsNounType(t))
    {
        return t != ObjectType::TEXT && t != ObjectType::EMPTY && t != ObjectType::ALL &&
               t != ObjectType::GROUP && t != ObjectType::LEVEL && t != ObjectType::CURSOR &&
               t != ObjectType::IMAGE;
    }
    if (t == ObjectType::IS) return true;
    if (IsOpType(t)) return false;  // HAS MAKE AND NOT ON NEAR FACING LONELY
    if (PropBit(t)) return true;
    // Properties with no runtime hook in Game.cpp are inert in engine and model alike.
    switch (t)
    {
        case ObjectType::PULL: case ObjectType::SWAP: case ObjectType::TELE:
        case ObjectType::FALL: case ObjectType::SHIFT: case ObjectType::MORE:
        case ObjectType::WORD: case ObjectType::BEST: case ObjectType::SLEEP:
        case ObjectType::RED: case ObjectType::BLUE: case ObjectType::HIDE:
        case ObjectType::BONUS: case ObjectType::END: case ObjectType::DONE:
            return true;
        default:
            return false;  // MOVE HOT MELT OPEN SHUT WEAK FLOAT SAFE UP DOWN LEFT RIGHT
    }
}

struct Rules
{
    std::uint8_t props[256] = { 0 };                         // by icon type
    std::vector<std::pair<std::uint8_t, std::uint8_t>> xf;   // (icon from, icon to), rule order
    std::vector<std::uint32_t> list;                         // subject<<8 | predicate, rule order
};

class Model
{
 public:
    using State = std::vector<std::uint16_t>;  // sorted (cell << 8 | type)

    int W = 0, H = 0;

    // Returns false when the level is outside the modelled subset.
    bool Init(const baba_is_auto::Game& game, State& out)
    {
        const baba_is_auto::Map& map = game.GetMap();
        W = static_cast<int>(map.GetWidth());
        H = static_cast<int>(map.GetHeight());
        if (W * H > 255) return false;
        out.clear();
        for (int y = 0; y < H; ++y)
            for (int x = 0; x < W; ++x)
            {
                int texts = 0;
                for (const auto& inst : map.At(x, y).GetInstances())
                {
                    if (inst.type == ObjectType::ICON_EMPTY) continue;
                    if (!IsModelWord(inst.type)) return false;
                    if (baba_is_auto::IsTextType(inst.type) && ++texts > 1) return false;
                    out.push_back(static_cast<std::uint16_t>(((y * W + x) << 8) |
                                                             static_cast<int>(inst.type)));
                }
            }
        std::sort(out.begin(), out.end());
        return true;
    }

    static std::string Key(const State& s)
    {
        return std::string(reinterpret_cast<const char*>(s.data()), s.size() * 2);
    }

    // Mirrors Game::ParseRules / Game::ParseRule for the subset: at every cell,
    // horizontally then vertically, NOUN IS (NOUN|PROPERTY).
    void Parse(const State& s, Rules& r) const
    {
        std::uint8_t text[256] = { 0 };
        for (auto o : s)
        {
            const int t = o & 0xff;
            if (t < static_cast<int>(ObjectType::ICON_TYPE)) text[o >> 8] = static_cast<std::uint8_t>(t);
        }
        const int iconBase = static_cast<int>(ObjectType::ICON_TYPE);
        const int is = static_cast<int>(ObjectType::IS);
        auto isNoun = [](int t) { return baba_is_auto::IsNounType(static_cast<ObjectType>(t)); };
        auto isProp = [](int t) { return baba_is_auto::IsPropertyType(static_cast<ObjectType>(t)); };
        for (int y = 0; y < H; ++y)
            for (int x = 0; x < W; ++x)
            {
                const int a = text[y * W + x];
                if (!a || !isNoun(a)) continue;
                for (int d = 0; d < 2; ++d)
                {
                    const int dx = d == 0, dy = d == 1;
                    if (x + 2 * dx >= W || y + 2 * dy >= H) continue;
                    const int b = text[(y + dy) * W + x + dx];
                    const int c = text[(y + 2 * dy) * W + x + 2 * dx];
                    if (b != is || !c) continue;
                    if (isNoun(c))
                    {
                        r.xf.emplace_back(static_cast<std::uint8_t>(a + iconBase),
                                          static_cast<std::uint8_t>(c + iconBase));
                        r.list.push_back((a << 8) | c);
                    }
                    else if (isProp(c))
                    {
                        r.props[a + iconBase] |= PropBit(static_cast<ObjectType>(c));
                        r.list.push_back((a << 8) | c);
                    }
                }
            }
    }

    struct Result
    {
        State next;
        bool won = false, lost = false, pushedIcon = false;
    };

    // Mirrors Game::MovePlayer for the subset.
    Result Step(const State& s, Direction dir) const
    {
        Result res;
        std::vector<Obj> objs;
        objs.reserve(s.size() + 4);
        for (auto o : s) objs.push_back({ static_cast<std::uint8_t>(o >> 8),
                                          static_cast<std::uint8_t>(o & 0xff), true });
        Rules rules;
        Parse(s, rules);

        bool textMoved = false;
        if (dir != Direction::NONE)
        {
            // Game::ProcessPlayerMove: collect YOU stacks, order them, move each.
            std::vector<int> stacks;
            for (const Obj& o : objs)
                if ((rules.props[o.type] & P_YOU) &&
                    std::find(stacks.begin(), stacks.end(), o.cell) == stacks.end())
                    stacks.push_back(o.cell);
            std::sort(stacks.begin(), stacks.end(), [&](int l, int r) {
                switch (dir)
                {
                    case Direction::LEFT: return l % W != r % W ? l % W < r % W : l < r;
                    case Direction::RIGHT: return l % W != r % W ? l % W > r % W : l < r;
                    case Direction::UP: return l / W != r / W ? l / W < r / W : l < r;
                    default: return l / W != r / W ? l / W > r / W : l < r;
                }
            });
            // player ids are captured before any stack moves (Game::GetPlayerIDsAt)
            std::vector<std::vector<int>> ids(stacks.size());
            for (std::size_t k = 0; k < stacks.size(); ++k)
                for (int i = 0; i < static_cast<int>(objs.size()); ++i)
                    if (objs[i].cell == stacks[k] && (rules.props[objs[i].type] & P_YOU))
                        ids[k].push_back(i);
            for (std::size_t k = 0; k < stacks.size(); ++k)
            {
                std::vector<int> movable;
                for (int i : ids[k])
                    if (objs[i].cell == stacks[k]) movable.push_back(i);  // still there?
                if (movable.empty()) continue;
                if (CanMove(objs, rules, stacks[k], dir))
                    ProcessMove(objs, rules, stacks[k], dir, movable, res.pushedIcon, textMoved);
            }
        }

        // ParseRules -> ProcessTransformations (snapshot based)
        // Rules can only have changed if a text tile moved.
        Rules r2 = rules;
        if (textMoved)
        {
            r2 = Rules();
            Parse(Pack(objs), r2);
        }
        if (!r2.xf.empty())
        {
            const std::size_t n = objs.size();
            for (std::size_t i = 0; i < n; ++i)
            {
                const std::uint8_t src = objs[i].type;
                std::vector<std::uint8_t> targets;
                bool identity = false;
                for (const auto& [from, to] : r2.xf)
                    if (from == src)
                    {
                        targets.push_back(to);
                        identity |= to == src;
                    }
                if (targets.empty() || identity) continue;
                objs[i].type = targets.front();
                for (std::size_t t = 1; t < targets.size(); ++t)
                    objs.push_back({ objs[i].cell, targets[t], true });
            }
            r2 = Rules();
            Parse(Pack(objs), r2);
        }

        // ProcessSink, ProcessDefeat, CheckPlayState all read the rules parsed above.
        int count[256] = { 0 };
        bool sink[256] = { false }, defeat[256] = { false }, win[256] = { false };
        for (const Obj& o : objs)
        {
            ++count[o.cell];
            sink[o.cell] |= (r2.props[o.type] & P_SINK) != 0;
        }
        for (Obj& o : objs)
            if (sink[o.cell] && count[o.cell] >= 2) o.alive = false;
        for (const Obj& o : objs)
            if (o.alive) defeat[o.cell] |= (r2.props[o.type] & P_DEFEAT) != 0;
        for (Obj& o : objs)
            if (o.alive && defeat[o.cell] && (r2.props[o.type] & P_YOU)) o.alive = false;
        bool hasPlayer = false;
        for (const Obj& o : objs)
            if (o.alive) win[o.cell] |= (r2.props[o.type] & P_WIN) != 0;
        for (const Obj& o : objs)
            if (o.alive && (r2.props[o.type] & P_YOU))
            {
                hasPlayer = true;
                res.won |= win[o.cell];
            }
        res.lost = !hasPlayer;
        res.next = Pack(objs);
        return res;
    }

 private:
    struct Obj
    {
        std::uint8_t cell, type;
        bool alive;
    };

    static bool IsText(std::uint8_t t) { return t < static_cast<int>(ObjectType::ICON_TYPE); }

    static State Pack(const std::vector<Obj>& objs)
    {
        State s;
        s.reserve(objs.size());
        for (const Obj& o : objs)
            if (o.alive) s.push_back(static_cast<std::uint16_t>((o.cell << 8) | o.type));
        std::sort(s.begin(), s.end());
        return s;
    }

    int Dest(int cell, Direction dir) const
    {
        int x = cell % W, y = cell / W;
        switch (dir)
        {
            case Direction::UP: --y; break;
            case Direction::DOWN: ++y; break;
            case Direction::LEFT: --x; break;
            case Direction::RIGHT: ++x; break;
            default: break;
        }
        return (x < 0 || x >= W || y < 0 || y >= H) ? -1 : y * W + x;
    }

    static bool Pushable(const Obj& o, const Rules& r)
    {
        return IsText(o.type) || (r.props[o.type] & P_PUSH);
    }

    // Mirrors Game::CanMove.
    bool CanMove(const std::vector<Obj>& objs, const Rules& r, int cell, Direction dir) const
    {
        const int d = Dest(cell, dir);
        if (d < 0) return false;
        bool anyPush = false;
        for (const Obj& o : objs)
        {
            if (o.cell != d) continue;
            if (!IsText(o.type) && (r.props[o.type] & P_STOP) && !(r.props[o.type] & P_PUSH))
                return false;
            anyPush |= Pushable(o, r);
        }
        if (anyPush && !CanMove(objs, r, d, dir)) return false;
        return true;
    }

    // Mirrors Game::ProcessMove / Game::ProcessPush.
    void ProcessMove(std::vector<Obj>& objs, const Rules& r, int cell, Direction dir,
                     const std::vector<int>& moving, bool& pushedIcon, bool& textMoved) const
    {
        const int d = Dest(cell, dir);
        std::vector<int> pushed;
        for (int i = 0; i < static_cast<int>(objs.size()); ++i)
            if (objs[i].cell == d && Pushable(objs[i], r)) pushed.push_back(i);
        if (!pushed.empty() && CanMove(objs, r, d, dir))
        {
            for (int i : pushed)
            {
                pushedIcon |= !IsText(objs[i].type) && !(r.props[objs[i].type] & P_YOU);
                textMoved |= IsText(objs[i].type);
            }
            ProcessMove(objs, r, d, dir, pushed, pushedIcon, textMoved);
        }
        for (int i : moving) objs[i].cell = static_cast<std::uint8_t>(d);
    }
};
}  // namespace forge

#endif
