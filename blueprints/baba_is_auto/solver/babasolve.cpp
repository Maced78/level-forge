// babasolve - state-space solver for baba-is-auto levels.
//
// Two interchangeable transition functions:
//   engine  the ORIGINAL baba_is_auto::Game (unmodified sources); every
//           successor is Game::MovePlayer on a copy of the real engine object.
//   model   model.hpp, a fast model of a documented subset of the engine,
//           differential-tested against the engine with --difftest.
// "auto" (default) uses the model when the level is inside the subset.
// Whatever finds a solution, callers certify it with --replay (real engine).
//
// usage: babasolve <level.txt> [--max-states N] [--max-ms T] [--forbid rules|push|win|you]...
//                  [--analyze] [--wait]
//                  [--backend auto|engine|model]
//        babasolve <level.txt> --replay MOVES   (frame-by-frame engine trace)
//        babasolve <level.txt> --difftest STEPS [--seed S]  (model vs engine)
// prints one JSON object on stdout.
#include <baba-is-auto/Games/Game.hpp>

#include "model.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <deque>
#include <iostream>
#include <map>
#include <random>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

using namespace baba_is_auto;

namespace
{
const char MOVE_CHARS[] = { 'U', 'D', 'L', 'R', 'W' };
const Direction MOVE_DIRS[] = { Direction::UP, Direction::DOWN,
                                Direction::LEFT, Direction::RIGHT,
                                Direction::NONE };

bool g_dirsMatter = false;

std::string StateKey(const Game& game)
{
    const Map& map = game.GetMap();
    std::string key;
    key.reserve(map.GetWidth() * map.GetHeight() * 3);
    std::vector<std::uint16_t> cell;

    for (std::size_t y = 0; y < map.GetHeight(); ++y)
    {
        for (std::size_t x = 0; x < map.GetWidth(); ++x)
        {
            cell.clear();
            for (const ObjectInstance& inst : map.At(x, y).GetInstances())
            {
                if (inst.type == ObjectType::ICON_EMPTY)
                {
                    continue;
                }
                auto v = static_cast<std::uint16_t>(
                    static_cast<int>(inst.type) * 8 +
                    (g_dirsMatter ? static_cast<int>(inst.direction) : 0));
                cell.push_back(v);
            }
            std::sort(cell.begin(), cell.end());
            for (auto v : cell)
            {
                key.push_back(static_cast<char>(v & 0xff));
                key.push_back(static_cast<char>(v >> 8));
            }
            key.push_back('\xff');
            key.push_back('\xff');
        }
    }
    return key;
}

// Signature of every active IS rule (optionally only those granting WIN).
std::string RuleSig(const Game& game, bool winOnly, ObjectType only = ObjectType::WIN)
{
    std::vector<std::string> sigs;
    RuleManager rm = const_cast<Game&>(game).GetRuleManager();
    for (const Rule& rule : rm.GetRules(ObjectType::IS))
    {
        const auto pred = std::get<2>(rule.objects).GetTypes();
        if (winOnly && std::find(pred.begin(), pred.end(), only) ==
                           pred.end())
        {
            continue;
        }
        std::string s;
        for (auto t : std::get<0>(rule.objects).GetTypes())
            s += std::to_string(static_cast<int>(t)) + ",";
        s += "|";
        for (auto t : pred) s += std::to_string(static_cast<int>(t)) + ",";
        s += "|";
        for (const auto& c : rule.conditions)
        {
            s += std::to_string(static_cast<int>(c.op)) + (c.negated ? "!" : "") + ":";
            for (auto t : c.targets) s += std::to_string(static_cast<int>(t)) + ",";
        }
        sigs.push_back(s);
    }
    std::sort(sigs.begin(), sigs.end());
    std::string out;
    for (auto& s : sigs) out += s + ";";
    return out;
}

// Positions of every non-text object that is not of a YOU-controlled type.
std::map<ObjectID, std::pair<std::size_t, std::size_t>> PushablePositions(
    const Game& game)
{
    std::set<ObjectType> youTypes;
    RuleManager rm = const_cast<Game&>(game).GetRuleManager();
    for (const Rule& rule : rm.GetRules(ObjectType::YOU))
    {
        for (auto t : std::get<0>(rule.objects).GetTypes())
            youTypes.insert(ConvertTextToIcon(t));
    }
    std::map<ObjectID, std::pair<std::size_t, std::size_t>> out;
    const Map& map = game.GetMap();
    for (std::size_t y = 0; y < map.GetHeight(); ++y)
        for (std::size_t x = 0; x < map.GetWidth(); ++x)
            for (const ObjectInstance& inst : map.At(x, y).GetInstances())
                if (IsIconType(inst.type) && inst.type != ObjectType::ICON_EMPTY &&
                    !youTypes.count(inst.type))
                    out[inst.id] = { x, y };
    return out;
}

bool PushHappened(const Game& before, const Game& after)
{
    const auto a = PushablePositions(before);
    const auto b = PushablePositions(after);
    for (const auto& [id, pos] : a)
    {
        auto it = b.find(id);
        if (it != b.end() && it->second != pos) return true;
    }
    return false;
}

std::string RulesJson(const Game& game)
{
    std::vector<std::string> out;
    RuleManager rm = const_cast<Game&>(game).GetRuleManager();
    for (ObjectType verb : { ObjectType::IS, ObjectType::HAS, ObjectType::MAKE })
    {
        for (const Rule& rule : rm.GetRules(verb))
        {
            const auto verbs = std::get<1>(rule.objects).GetTypes();
            if (std::find(verbs.begin(), verbs.end(), verb) == verbs.end()) continue;
            std::string s = "[";
            bool first = true;
            auto add = [&s, &first](int v) {
                s += (first ? "" : ",") + std::to_string(v);
                first = false;
            };
            for (auto t : std::get<0>(rule.objects).GetTypes()) add(static_cast<int>(t));
            for (const auto& c : rule.conditions)
            {
                if (c.negated) add(static_cast<int>(ObjectType::NOT));
                add(static_cast<int>(c.op));
                for (auto t : c.targets) add(static_cast<int>(t));
            }
            add(static_cast<int>(verb));
            for (auto t : std::get<2>(rule.objects).GetTypes()) add(static_cast<int>(t));
            s += "]";
            if (std::find(out.begin(), out.end(), s) == out.end()) out.push_back(s);
        }
    }
    std::sort(out.begin(), out.end());
    std::string j = "[";
    for (std::size_t i = 0; i < out.size(); ++i) j += (i ? "," : "") + out[i];
    return j + "]";
}

std::string FrameJson(const Game& game)
{
    const Map& map = game.GetMap();
    std::string j = "{\"state\":\"";
    const PlayState ps = game.GetPlayState();
    j += ps == PlayState::WON ? "WON" : ps == PlayState::LOST ? "LOST"
         : ps == PlayState::PLAYING ? "PLAYING" : "INVALID";
    j += "\",\"player_icon\":" + std::to_string(static_cast<int>(game.GetPlayerIcon()));
    j += ",\"rules\":" + RulesJson(game) + ",\"cells\":[";
    bool firstCell = true;
    for (std::size_t y = 0; y < map.GetHeight(); ++y)
        for (std::size_t x = 0; x < map.GetWidth(); ++x)
            for (const ObjectInstance& inst : map.At(x, y).GetInstances())
            {
                if (inst.type == ObjectType::ICON_EMPTY) continue;
                j += std::string(firstCell ? "" : ",") + "[" + std::to_string(x) + "," +
                     std::to_string(y) + "," + std::to_string(static_cast<int>(inst.type)) +
                     "," + std::to_string(static_cast<int>(inst.direction)) + "," +
                     std::to_string(inst.id) + "]";
                firstCell = false;
            }
    return j + "]}";
}

int Replay(const std::string& file, const std::string& moves)
{
    try
    {
        Game game(file);
        game.SetRandomSeed(0);
        std::cout << "{\"status\":\"ok\",\"width\":" << game.GetMap().GetWidth()
                  << ",\"height\":" << game.GetMap().GetHeight() << ",\"frames\":["
                  << FrameJson(game);
        for (char c : moves)
        {
            Direction d = c == 'U' ? Direction::UP : c == 'D' ? Direction::DOWN
                          : c == 'L' ? Direction::LEFT : c == 'R' ? Direction::RIGHT
                          : Direction::NONE;
            game.MovePlayer(d);
            std::cout << "," << FrameJson(game);
        }
        std::cout << "]}\n";
    }
    catch (const std::exception& e)
    {
        std::cout << "{\"status\":\"load_error\",\"error\":\"" << e.what() << "\"}\n";
    }
    return 0;
}


struct Node
{
    std::int32_t parent;
    char move;
    std::int32_t depth;
    bool won;
    bool lost;
};

struct Options
{
    std::size_t maxStates = 200000;
    double maxMs = 20000;
    bool forbidRules = false, forbidPush = false, forbidWin = false, forbidYou = false;
    bool analyze = false, allowWait = false;
};

struct Successor
{
    bool won = false, lost = false, pruned = false;
    std::string key;
};

// Backend concept: State; Key(State); Expand(State, move, opts, Successor&) -> State
struct EngineBackend
{
    using State = Game;
    static constexpr const char* name = "engine";
    static std::string Key(const State& g) { return StateKey(g); }
    State Expand(const State& game, int m, const Options& o, Successor& out) const
    {
        Game next = game;
        next.MovePlayer(MOVE_DIRS[m]);
        if ((o.forbidRules && RuleSig(next, false) != RuleSig(game, false)) ||
            (o.forbidWin && RuleSig(next, true) != RuleSig(game, true)) ||
            (o.forbidYou && RuleSig(next, true, ObjectType::YOU) !=
                                RuleSig(game, true, ObjectType::YOU)) ||
            (o.forbidPush && PushHappened(game, next)))
        {
            out.pruned = true;
            return next;
        }
        out.won = next.GetPlayState() == PlayState::WON;
        out.lost = !out.won && (next.GetPlayState() == PlayState::LOST ||
                                next.GetPlayerIcon() == ObjectType::ICON_EMPTY);
        out.key = StateKey(next);
        return next;
    }
};

struct ModelBackend
{
    using State = forge::Model::State;
    static constexpr const char* name = "model";
    forge::Model model;
    static std::string Key(const State& s) { return forge::Model::Key(s); }

    static std::vector<std::uint32_t> Sig(const forge::Rules& r, int only)
    {
        std::vector<std::uint32_t> v;
        for (auto x : r.list)
            if (only < 0 || static_cast<int>(x & 0xff) == only) v.push_back(x);
        std::sort(v.begin(), v.end());
        return v;
    }

    State Expand(const State& s, int m, const Options& o, Successor& out) const
    {
        auto res = model.Step(s, MOVE_DIRS[m]);
        if (o.forbidPush && res.pushedIcon) out.pruned = true;
        if (!out.pruned && (o.forbidRules || o.forbidWin || o.forbidYou))
        {
            forge::Rules a, b;
            model.Parse(s, a);
            model.Parse(res.next, b);
            if ((o.forbidRules && Sig(a, -1) != Sig(b, -1)) ||
                (o.forbidWin && Sig(a, static_cast<int>(ObjectType::WIN)) !=
                                    Sig(b, static_cast<int>(ObjectType::WIN))) ||
                (o.forbidYou && Sig(a, static_cast<int>(ObjectType::YOU)) !=
                                    Sig(b, static_cast<int>(ObjectType::YOU))))
                out.pruned = true;
        }
        if (out.pruned) return res.next;
        out.won = res.won;
        out.lost = !res.won && res.lost;
        out.key = Key(res.next);
        return res.next;
    }
};

template <class Backend>
void Search(const Backend& be, const typename Backend::State& root, bool rootWon,
            bool rootLost, const Options& opt, bool dirsInState)
{
    const auto t0 = std::chrono::steady_clock::now();
    auto elapsedMs = [&t0]() {
        return std::chrono::duration<double, std::milli>(
                   std::chrono::steady_clock::now() - t0).count();
    };
    const int numMoves = opt.allowWait ? 5 : 4;
    std::vector<Node> nodes;
    std::vector<std::array<std::int32_t, 5>> succ;
    std::unordered_map<std::string, std::int32_t> seen;
    std::deque<std::pair<std::int32_t, typename Backend::State>> frontier;
    const std::array<std::int32_t, 5> none = { -1, -1, -1, -1, -1 };

    nodes.push_back({ -1, 0, 0, rootWon, rootLost });
    succ.push_back(none);
    seen.emplace(Backend::Key(root), 0);
    if (!rootWon && !rootLost) frontier.emplace_back(0, root);

    std::int32_t firstWin = rootWon ? 0 : -1;
    bool capped = false;
    std::int32_t expandedDepth = -1;  // every node of this depth or less has been expanded

    while (!frontier.empty())
    {
        if (!opt.analyze && firstWin >= 0) break;
        if (nodes.size() >= opt.maxStates || ((nodes.size() & 255) == 0 && elapsedMs() > opt.maxMs))
        {
            capped = true;
            break;
        }
        auto [idx, state] = std::move(frontier.front());
        frontier.pop_front();
        expandedDepth = nodes[idx].depth - 1;

        for (int m = 0; m < numMoves; ++m)
        {
            Successor sc;
            auto next = be.Expand(state, m, opt, sc);
            if (sc.pruned) continue;
            if (sc.won) sc.key += "W";
            auto [it, inserted] =
                seen.emplace(std::move(sc.key), static_cast<std::int32_t>(nodes.size()));
            succ[idx][m] = it->second;
            if (!inserted) continue;
            nodes.push_back({ idx, MOVE_CHARS[m], nodes[idx].depth + 1, sc.won, sc.lost });
            succ.push_back(none);
            if (sc.won)
            {
                if (firstWin < 0) firstWin = it->second;
            }
            else if (!sc.lost)
            {
                frontier.emplace_back(it->second, std::move(next));
            }
        }
    }

    std::string moves;
    if (firstWin >= 0)
    {
        for (std::int32_t n = firstWin; nodes[n].parent >= 0; n = nodes[n].parent)
            moves.push_back(nodes[n].move);
        std::reverse(moves.begin(), moves.end());
    }

    const bool exhaustive = !capped && frontier.empty();
    const bool countExact = firstWin >= 0 &&
                            (exhaustive || expandedDepth >= nodes[firstWin].depth - 1);
    std::cout << "{\"status\":\""
              << (firstWin >= 0 ? "solved" : (exhaustive ? "unsolvable" : "unknown"))
              << "\",\"proof\":\""
              << (firstWin >= 0 ? "witness" : (exhaustive ? "exhaustive" : "bounded"))
              << "\",\"backend\":\"" << Backend::name << "\",\"moves\":\"" << moves
              << "\",\"length\":" << moves.size() << ",\"states_explored\":" << nodes.size()
              << ",\"max_states\":" << opt.maxStates
              << ",\"directions_in_state\":" << (dirsInState ? "true" : "false")
              << ",\"wait_allowed\":" << (opt.allowWait ? "true" : "false")
              << ",\"won_at_load\":" << (rootWon ? "true" : "false")
              << ",\"no_player_at_load\":" << (rootLost ? "true" : "false");

    if (opt.analyze)
    {
        // Backward reachability from winning states: a state is "dead" if no
        // sequence of moves from it reaches a win (soft lock or loss).
        const std::size_t n = nodes.size();
        std::vector<std::vector<std::int32_t>> pred(n);
        for (std::size_t i = 0; i < n; ++i)
            for (int m = 0; m < numMoves; ++m)
                if (succ[i][m] >= 0) pred[succ[i][m]].push_back(static_cast<std::int32_t>(i));
        std::vector<char> canWin(n, 0);
        std::deque<std::int32_t> q;
        std::size_t wins = 0, losts = 0;
        for (std::size_t i = 0; i < n; ++i)
        {
            if (nodes[i].won)
            {
                canWin[i] = 1;
                q.push_back(static_cast<std::int32_t>(i));
                ++wins;
            }
            if (nodes[i].lost) ++losts;
        }
        while (!q.empty())
        {
            auto i = q.front();
            q.pop_front();
            for (auto p : pred[i])
                if (!canWin[p])
                {
                    canWin[p] = 1;
                    q.push_back(p);
                }
        }
        std::size_t dead = 0;
        for (std::size_t i = 0; i < n; ++i)
            if (!canWin[i]) ++dead;

        // Number of distinct shortest winning move sequences (BFS order => depth sorted).
        double shortestCount = 0;
        if (firstWin >= 0)
        {
            const int target = nodes[firstWin].depth;
            std::vector<double> ways(n, 0);
            ways[0] = 1;
            for (std::size_t i = 0; i < n; ++i)
            {
                if (nodes[i].won || nodes[i].depth >= target) continue;
                for (int m = 0; m < numMoves; ++m)
                {
                    auto s = succ[i][m];
                    if (s >= 0 && nodes[s].depth == nodes[i].depth + 1) ways[s] += ways[i];
                }
            }
            for (std::size_t i = 0; i < n; ++i)
                if (nodes[i].won && nodes[i].depth == target) shortestCount += ways[i];
        }
        // Trap metrics along the shortest solution (only meaningful when the
        // whole state space was enumerated, otherwise "dead" is not known).
        //   decision_points  path states with at least one move that changes the state
        //   trap_states      path states where at least one such move leads to a dead state
        //   forced_states    path states where exactly one distinct successor keeps the level winnable
        //   survival         product over path states of (winnable successors / state-changing moves):
        //                    the chance that a player picking uniformly among state-changing moves
        //                    at each step of the solution never makes the level unwinnable
        std::size_t decisionPoints = 0, trapStates = 0, forcedStates = 0, trapMoves = 0;
        double survivalLog2 = 0;
        if (firstWin >= 0 && exhaustive)
        {
            std::vector<std::int32_t> path;
            for (std::int32_t v = firstWin; v >= 0; v = nodes[v].parent) path.push_back(v);
            std::reverse(path.begin(), path.end());
            for (std::size_t k = 0; k + 1 < path.size(); ++k)
            {
                const auto v = path[k];
                int changing = 0, safe = 0;
                std::vector<std::int32_t> safeSucc;
                for (int mv = 0; mv < numMoves; ++mv)
                {
                    const auto t = succ[v][mv];
                    if (t < 0 || t == v) continue;
                    ++changing;
                    if (canWin[t])
                    {
                        ++safe;
                        if (std::find(safeSucc.begin(), safeSucc.end(), t) == safeSucc.end())
                            safeSucc.push_back(t);
                    }
                }
                if (changing == 0 || safe == 0) continue;
                ++decisionPoints;
                if (safe < changing)
                {
                    ++trapStates;
                    trapMoves += changing - safe;
                }
                if (safeSucc.size() == 1) ++forcedStates;
                survivalLog2 += std::log2(static_cast<double>(safe) / changing);
            }
        }
        std::cout << ",\"path\":{\"established\":" << ((firstWin >= 0 && exhaustive) ? "true" : "false")
                  << ",\"decision_points\":" << decisionPoints << ",\"trap_states\":" << trapStates
                  << ",\"trap_moves\":" << trapMoves << ",\"forced_states\":" << forcedStates
                  << ",\"survival_log2\":" << survivalLog2 << "}";
        std::cout << ",\"analysis\":{\"complete\":" << (exhaustive ? "true" : "false")
                  << ",\"reachable_states\":" << n << ",\"winning_states\":" << wins
                  << ",\"lost_states\":" << losts << ",\"dead_states\":" << dead
                  << ",\"shortest_solution_count\":" << shortestCount
                  << ",\"shortest_count_exact\":" << (countExact ? "true" : "false") << "}";
    }
    std::cout << ",\"elapsed_ms\":" << elapsedMs() << "}\n";
}

// Random walk in lock-step: the model and the real engine must agree on the
// whole board and on win/lose after every single move.
int DiffTest(const std::string& file, long steps, unsigned seed)
{
    Game root(file);
    root.SetRandomSeed(0);
    forge::Model model;
    forge::Model::State s0;
    if (!model.Init(root, s0))
    {
        std::cout << "{\"status\":\"not_eligible\"}\n";
        return 0;
    }
    auto engineState = [&model](const Game& g) {
        forge::Model::State s;
        const Map& map = g.GetMap();
        for (int y = 0; y < model.H; ++y)
            for (int x = 0; x < model.W; ++x)
                for (const auto& inst : map.At(x, y).GetInstances())
                    if (inst.type != ObjectType::ICON_EMPTY)
                        s.push_back(static_cast<std::uint16_t>(((y * model.W + x) << 8) |
                                                               static_cast<int>(inst.type)));
        std::sort(s.begin(), s.end());
        return s;
    };
    std::mt19937 rng(seed);
    Game game = root;
    forge::Model::State s = s0;
    long done = 0, episodes = 1, wins = 0, losses = 0;
    std::string path;
    for (; done < steps; ++done)
    {
        const int m = static_cast<int>(rng() % 4);
        path.push_back(MOVE_CHARS[m]);
        game.MovePlayer(MOVE_DIRS[m]);
        auto res = model.Step(s, MOVE_DIRS[m]);
        const bool eWon = game.GetPlayState() == PlayState::WON;
        const bool eLost = !eWon && (game.GetPlayState() == PlayState::LOST ||
                                     game.GetPlayerIcon() == ObjectType::ICON_EMPTY);
        const bool mLost = !res.won && res.lost;
        if (engineState(game) != res.next || eWon != res.won || eLost != mLost)
        {
            std::cout << "{\"status\":\"mismatch\",\"steps\":" << done << ",\"path\":\"" << path
                      << "\",\"engine_won\":" << eWon << ",\"model_won\":" << res.won
                      << ",\"engine_lost\":" << eLost << ",\"model_lost\":" << mLost << "}\n";
            return 1;
        }
        s = res.next;
        if (eWon || eLost || path.size() > 400)
        {
            wins += eWon;
            losses += eLost;
            game = root;
            s = s0;
            path.clear();
            ++episodes;
        }
    }
    std::cout << "{\"status\":\"agree\",\"steps\":" << done << ",\"episodes\":" << episodes
              << ",\"wins\":" << wins << ",\"losses\":" << losses << "}\n";
    return 0;
}
}  // namespace

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        std::cerr << "usage: babasolve <level.txt> [--max-states N] [--max-ms T] "
                     "[--forbid rules|push|win|you] [--analyze] [--wait] "
                     "[--backend auto|engine|model]\n"
                     "       babasolve <level.txt> --replay MOVES\n"
                     "       babasolve <level.txt> --difftest STEPS [--seed S]\n";
        return 2;
    }
    std::string file = argv[1];
    Options opt;
    std::string backend = "auto";
    long diffSteps = -1;
    unsigned seed = 1;
    for (int i = 2; i < argc; ++i)
    {
        std::string a = argv[i];
        if (a == "--max-states" && i + 1 < argc) opt.maxStates = std::stoull(argv[++i]);
        else if (a == "--max-ms" && i + 1 < argc) opt.maxMs = std::stod(argv[++i]);
        else if (a == "--backend" && i + 1 < argc) backend = argv[++i];
        else if (a == "--seed" && i + 1 < argc) seed = static_cast<unsigned>(std::stoul(argv[++i]));
        else if (a == "--difftest" && i + 1 < argc) diffSteps = std::stol(argv[++i]);
        else if (a == "--forbid" && i + 1 < argc)
        {
            std::string f = argv[++i];
            opt.forbidRules |= f == "rules";
            opt.forbidPush |= f == "push";
            opt.forbidWin |= f == "win";
            opt.forbidYou |= f == "you";
        }
        else if (a == "--analyze") opt.analyze = true;
        else if (a == "--wait") opt.allowWait = true;
        else if (a == "--replay") return Replay(file, i + 1 < argc ? argv[i + 1] : "");
    }

    try
    {
        if (diffSteps >= 0) return DiffTest(file, diffSteps, seed);
        Game root(file);
        root.SetRandomSeed(0);

        // Facing directions are part of the engine state key only if some text
        // tile can make them observable (MOVE, FACING or a direction property).
        const Map& map = root.GetMap();
        for (std::size_t y = 0; y < map.GetHeight(); ++y)
            for (std::size_t x = 0; x < map.GetWidth(); ++x)
                for (const auto& inst : map.At(x, y).GetInstances())
                {
                    auto t = inst.type;
                    if (t == ObjectType::MOVE || t == ObjectType::FACING ||
                        t == ObjectType::UP || t == ObjectType::DOWN ||
                        t == ObjectType::LEFT || t == ObjectType::RIGHT || IsLockedType(t))
                        g_dirsMatter = true;
                }
        const bool rootWon = root.GetPlayState() == PlayState::WON;
        const bool rootLost = root.GetPlayState() == PlayState::LOST ||
                              root.GetPlayerIcon() == ObjectType::ICON_EMPTY;

        ModelBackend mb;
        ModelBackend::State s0;
        const bool eligible = mb.model.Init(root, s0);
        if (backend == "model" && !eligible)
        {
            std::cout << "{\"status\":\"not_eligible\",\"error\":\"level uses words outside the "
                         "modelled subset; use --backend engine\"}\n";
            return 0;
        }
        if (backend == "engine" || !eligible)
            Search(EngineBackend{}, root, rootWon, rootLost, opt, g_dirsMatter);
        else
            Search(mb, s0, rootWon, rootLost, opt, false);
    }
    catch (const std::exception& e)
    {
        std::cout << "{\"status\":\"load_error\",\"error\":\"" << e.what() << "\"}\n";
    }
    return 0;
}
