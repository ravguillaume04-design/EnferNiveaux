package enferplugins.niveaux.commands;

import enferplugins.niveaux.NiveauxPlugin;
import enferplugins.niveaux.data.PlayerData;
import enferplugins.niveaux.events.PlayerLevelChangeEvent;
import enferplugins.niveaux.util.ColorUtil;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.util.List;
import java.util.function.Consumer;
import java.util.stream.Stream;

public class NiveauCommand implements CommandExecutor, TabCompleter {

    private static final List<String> ADMIN_ACTIONS = List.of("add", "remove", "set", "reset");
    private final NiveauxPlugin plugin;

    public NiveauCommand(NiveauxPlugin plugin) { this.plugin = plugin; }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length < 1) {
            if (sender.hasPermission("niveaux.admin")) sendHelp(sender);
            else sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau &#FFFFFF<pseudo>"));
            return true;
        }

        String sub = args[0].toLowerCase();

        // Commandes admin
        if (ADMIN_ACTIONS.contains(sub)) {
            if (!sender.hasPermission("niveaux.admin")) {
                sender.sendMessage(ColorUtil.colorize("&#FF5555Vous n'avez pas la permission d'utiliser cette commande."));
                return true;
            }
            switch (sub) {
                case "reset"  -> handleReset(sender, args);
                case "add"    -> handleAdd(sender, args);
                case "remove" -> handleRemove(sender, args);
                case "set"    -> handleSet(sender, args);
            }
            return true;
        }

        // Commande de consultation : /niveau <pseudo>
        if (!sender.hasPermission("niveaux.see") && !sender.hasPermission("niveaux.admin")) {
            sender.sendMessage(ColorUtil.colorize("&#FF5555Vous n'avez pas la permission d'utiliser cette commande."));
            return true;
        }
        handleCheck(sender, args[0]);
        return true;
    }

    private void handleCheck(CommandSender sender, String targetName) {
        Player online = Bukkit.getPlayerExact(targetName);
        if (online != null) {
            PlayerData cached = plugin.getPlayerCache().get(online.getUniqueId());
            if (cached != null) {
                sendLevelInfo(sender, cached);
                return;
            }
        }
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayerByName(targetName);
            Bukkit.getScheduler().runTask(plugin, () -> {
                if (data == null) {
                    sender.sendMessage(ColorUtil.colorize("&#FF5555Joueur &#FFFFFF" + targetName + " &#FF5555introuvable en base de donn\u00e9es."));
                    return;
                }
                sendLevelInfo(sender, data);
            });
        });
    }

    private void sendLevelInfo(CommandSender sender, PlayerData data) {
        sender.sendMessage(ColorUtil.colorize(
            "&#FFFFFF" + data.getName() + " &#606060\u00bb Niveau &#FFB300" + data.getLevel() +
            " &#606060(" + data.getMinutes() + " min de temps de jeu)"
        ));
    }

    private void handleReset(CommandSender sender, String[] args) {
        if (args.length < 2) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau reset &#FFFFFF<pseudo>")); return; }
        modifyData(sender, args[1], data -> {
            int old = data.getLevel(); data.reset();
            Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(data.getUuid(), data.getName(), old, 0, PlayerLevelChangeEvent.Reason.ADMIN_RESET));
            sender.sendMessage(ColorUtil.colorize("&#55FF55Le niveau de &#FFFFFF" + data.getName() + " &#55FF55a \u00e9t\u00e9 r\u00e9initialis\u00e9. &#606060(ancien niveau : &#FFB300" + old + "&#606060)"));
        });
    }

    private void handleAdd(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau add &#FFFFFF<valeur> <pseudo>")); return; }
        int amount = parseNonNegativeInt(sender, args[1]); if (amount < 0) return;
        modifyData(sender, args[2], data -> {
            int old = data.getLevel(); data.addLevel(amount);
            Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(data.getUuid(), data.getName(), old, data.getLevel(), PlayerLevelChangeEvent.Reason.ADMIN_ADD));
            sender.sendMessage(ColorUtil.colorize("&#55FF55+" + amount + " niveau(x) ajout\u00e9(s) \u00e0 &#FFFFFF" + data.getName() + "&#55FF55. &#606060(&#FFB300" + old + " &#606060\u2192 &#FFB300" + data.getLevel() + "&#606060)"));
        });
    }

    private void handleRemove(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau remove &#FFFFFF<valeur> <pseudo>")); return; }
        int amount = parseNonNegativeInt(sender, args[1]); if (amount < 0) return;
        modifyData(sender, args[2], data -> {
            int old = data.getLevel(); data.removeLevel(amount);
            Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(data.getUuid(), data.getName(), old, data.getLevel(), PlayerLevelChangeEvent.Reason.ADMIN_REMOVE));
            sender.sendMessage(ColorUtil.colorize("&#FF5555-" + amount + " niveau(x) retir\u00e9(s) \u00e0 &#FFFFFF" + data.getName() + "&#FF5555. &#606060(&#FFB300" + old + " &#606060\u2192 &#FFB300" + data.getLevel() + "&#606060)"));
        });
    }

    private void handleSet(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau set &#FFFFFF<valeur> <pseudo>")); return; }
        int level = parseNonNegativeInt(sender, args[1]); if (level < 0) return;
        modifyData(sender, args[2], data -> {
            int old = data.getLevel(); data.setLevel(level);
            Bukkit.getPluginManager().callEvent(new PlayerLevelChangeEvent(data.getUuid(), data.getName(), old, data.getLevel(), PlayerLevelChangeEvent.Reason.ADMIN_SET));
            sender.sendMessage(ColorUtil.colorize("&#55FF55Niveau de &#FFFFFF" + data.getName() + " &#55FF55d\u00e9fini \u00e0 &#FFB300" + data.getLevel() + "&#55FF55. &#606060(&#FFB300" + old + " &#606060\u2192 &#FFB300" + data.getLevel() + "&#606060, temps recalcul\u00e9 : &#FFFF55" + data.getMinutes() + " &#606060min)"));
        });
    }

    /**
     * Modifie les donnees d'un joueur et met a jour le cache si le joueur est en ligne.
     *
     * Cas 1 : joueur en ligne ET dans le cache  -> modification directe du cache + save async.
     * Cas 2 : joueur en ligne mais PAS dans le cache (chargement async login pas encore fini)
     *          -> chargement depuis la DB par UUID, modification, mise en cache, save async.
     * Cas 3 : joueur hors ligne -> chargement par pseudo, modification si trouve, save async.
     */
    private void modifyData(CommandSender sender, String targetName, Consumer<PlayerData> modifier) {
        Player online = Bukkit.getPlayerExact(targetName);

        if (online != null) {
            PlayerData cached = plugin.getPlayerCache().get(online.getUniqueId());
            if (cached != null) {
                modifier.accept(cached);
                Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> plugin.getDatabaseManager().savePlayer(cached));
                return;
            }
            // En ligne mais cache vide : charger par UUID et mettre en cache
            final Player onlineRef = online;
            Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
                PlayerData data = plugin.getDatabaseManager().loadPlayer(onlineRef.getUniqueId(), onlineRef.getName());
                Bukkit.getScheduler().runTask(plugin, () -> {
                    modifier.accept(data);
                    plugin.getPlayerCache().put(onlineRef.getUniqueId(), data);
                    Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> plugin.getDatabaseManager().savePlayer(data));
                });
            });
            return;
        }

        // Joueur hors ligne
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayerByName(targetName);
            Bukkit.getScheduler().runTask(plugin, () -> {
                if (data == null) {
                    sender.sendMessage(ColorUtil.colorize("&#FF5555Joueur &#FFFFFF" + targetName + " &#FF5555introuvable en base de donn\u00e9es."));
                    return;
                }
                modifier.accept(data);
                Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> plugin.getDatabaseManager().savePlayer(data));
            });
        });
    }

    private int parseNonNegativeInt(CommandSender sender, String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value < 0) { sender.sendMessage(ColorUtil.colorize("&#FF5555La valeur doit \u00eatre un entier positif ou z\u00e9ro.")); return -1; }
            return value;
        } catch (NumberFormatException e) {
            sender.sendMessage(ColorUtil.colorize("&#FF5555&#FFFFFF" + raw + " &#FF5555n'est pas un nombre valide."));
            return -1;
        }
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(ColorUtil.colorize("&#FFB300&l=== Commandes /niveau ==="));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau &#FFFFFF<pseudo>               &#606060- Voir le niveau d'un joueur"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau add &#FFFFFF<valeur> <pseudo>    &#606060- Ajouter des niveaux"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau remove &#FFFFFF<valeur> <pseudo> &#606060- Retirer des niveaux"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau set &#FFFFFF<valeur> <pseudo>    &#606060- D\u00e9finir un niveau pr\u00e9cis"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau reset &#FFFFFF<pseudo>           &#606060- Remettre \u00e0 z\u00e9ro"));
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        boolean isAdmin = sender.hasPermission("niveaux.admin");
        boolean canSee = sender.hasPermission("niveaux.see");
        if (!isAdmin && !canSee) return List.of();
        if (args.length == 1) {
            List<String> players = onlinePlayers(args[0]);
            if (isAdmin) {
                List<String> actions = ADMIN_ACTIONS.stream()
                    .filter(a -> a.startsWith(args[0].toLowerCase())).toList();
                return Stream.concat(actions.stream(),
                    players.stream().filter(p -> ADMIN_ACTIONS.stream().noneMatch(a -> a.equalsIgnoreCase(p)))).toList();
            }
            return players;
        }
        if (!isAdmin) return List.of();
        String action = args[0].toLowerCase();
        if (args.length == 2 && action.equals("reset")) return onlinePlayers(args[1]);
        if (args.length == 3 && (action.equals("add") || action.equals("remove") || action.equals("set"))) return onlinePlayers(args[2]);
        return List.of();
    }

    private List<String> onlinePlayers(String prefix) {
        return Bukkit.getOnlinePlayers().stream()
            .map(Player::getName)
            .filter(n -> n.toLowerCase().startsWith(prefix.toLowerCase()))
            .toList();
    }
}
