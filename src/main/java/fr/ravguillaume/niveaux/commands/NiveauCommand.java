package fr.ravguillaume.niveaux.commands;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import fr.ravguillaume.niveaux.util.ColorUtil;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.util.List;
import java.util.function.Consumer;

/**
 * Commandes administrateur pour gérer les niveaux des joueurs.
 *
 * Usage :
 *   /niveau reset  <pseudo>
 *   /niveau add    <valeur> <pseudo>
 *   /niveau remove <valeur> <pseudo>
 *   /niveau set    <valeur> <pseudo>
 */
public class NiveauCommand implements CommandExecutor, TabCompleter {

    private static final List<String> ACTIONS = Arrays.asList(
            "add", "remove", "set", "reset"
    );

    private final NiveauxPlugin plugin;

    public NiveauCommand(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    // -------------------------------------------------------------------------
    // CommandExecutor
    // -------------------------------------------------------------------------

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("niveaux.admin")) {
            sender.sendMessage(ColorUtil.colorize("&#FF5555Vous n'avez pas la permission d'utiliser cette commande."));
            return true;
        }

        if (args.length < 1) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "reset"  -> handleReset(sender, args);
            case "add"    -> handleAdd(sender, args);
            case "remove" -> handleRemove(sender, args);
            case "set"    -> handleSet(sender, args);
            default       -> sendHelp(sender);
        }
        return true;
    }

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    private void handleReset(CommandSender sender, String[] args) {
        if (args.length < 2) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau reset &#FFFFFF<pseudo>")); return; }

        modifyData(sender, args[1], data -> {
            int old = data.getLevel();
            data.reset();
            sender.sendMessage(ColorUtil.colorize(
                "&#55FF55Le niveau de &#FFFFFF" + data.getName() + " &#55FF55a été réinitialisé. " +
                "&#606060(ancien niveau : &#FFB300" + old + "&#606060)"
            ));
        });
    }

    private void handleAdd(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau add &#FFFFFF<valeur> <pseudo>")); return; }

        int amount = parseNonNegativeInt(sender, args[1]);
        if (amount < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.addLevel(amount);
            sender.sendMessage(ColorUtil.colorize(
                "&#55FF55+" + amount + " niveau(x) ajouté(s) à &#FFFFFF" + data.getName() +
                "&#55FF55. &#606060(&#FFB300" + old + " &#606060→ &#FFB300" + data.getLevel() + "&#606060)"
            ));
        });
    }

    private void handleRemove(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau remove &#FFFFFF<valeur> <pseudo>")); return; }

        int amount = parseNonNegativeInt(sender, args[1]);
        if (amount < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.removeLevel(amount);
            sender.sendMessage(ColorUtil.colorize(
                "&#FF5555-" + amount + " niveau(x) retiré(s) à &#FFFFFF" + data.getName() +
                "&#FF5555. &#606060(&#FFB300" + old + " &#606060→ &#FFB300" + data.getLevel() + "&#606060)"
            ));
        });
    }

    private void handleSet(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage(ColorUtil.colorize("&#FF5555Usage : &#FFB300/niveau set &#FFFFFF<valeur> <pseudo>")); return; }

        int level = parseNonNegativeInt(sender, args[1]);
        if (level < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.setLevel(level);
            sender.sendMessage(ColorUtil.colorize(
                "&#55FF55Niveau de &#FFFFFF" + data.getName() + " &#55FF55défini à &#FFB300" + data.getLevel() +
                "&#55FF55. &#606060(&#FFB300" + old + " &#606060→ &#FFB300" + data.getLevel() +
                "&#606060, temps recalculé : &#FFFF55" + data.getMinutes() + " &#606060min)"
            ));
        });
    }

    // -------------------------------------------------------------------------
    // Résolution des données (cache → DB)
    // -------------------------------------------------------------------------

    /**
     * Résout les données d'un joueur (modification) et exécute le callback
     * sur le thread principal. Sauvegarde automatiquement après modification.
     */
    private void modifyData(CommandSender sender, String targetName, Consumer<PlayerData> modifier) {
        Player online = Bukkit.getPlayerExact(targetName);
        if (online != null) {
            PlayerData cached = plugin.getPlayerCache().get(online.getUniqueId());
            if (cached != null) {
                modifier.accept(cached);
                // Sauvegarde asynchrone immédiate
                Bukkit.getScheduler().runTaskAsynchronously(plugin, () ->
                    plugin.getDatabaseManager().savePlayer(cached)
                );
                return;
            }
        }

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayerByName(targetName);
            Bukkit.getScheduler().runTask(plugin, () -> {
                if (data == null) {
                    sender.sendMessage(ColorUtil.colorize("&#FF5555Joueur &#FFFFFF" + targetName + " &#FF5555introuvable en base de données."));
                    return;
                }
                modifier.accept(data);
                Bukkit.getScheduler().runTaskAsynchronously(plugin, () ->
                    plugin.getDatabaseManager().savePlayer(data)
                );
            });
        });
    }

    // -------------------------------------------------------------------------
    // Utilitaires
    // -------------------------------------------------------------------------

    /**
     * Parse un entier >= 0. Retourne -1 (et envoie un message d'erreur) si invalide.
     */
    private int parseNonNegativeInt(CommandSender sender, String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value < 0) {
                sender.sendMessage(ColorUtil.colorize("&#FF5555La valeur doit être un entier positif ou zéro."));
                return -1;
            }
            return value;
        } catch (NumberFormatException e) {
            sender.sendMessage(ColorUtil.colorize("&#FF5555&#FFFFFF" + raw + " &#FF5555n'est pas un nombre valide."));
            return -1;
        }
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(ColorUtil.colorize("&#FFB300&l=== Commandes /niveau ==="));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau add &#FFFFFF<valeur> <pseudo>    &#606060- Ajouter des niveaux"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau remove &#FFFFFF<valeur> <pseudo> &#606060- Retirer des niveaux"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau set &#FFFFFF<valeur> <pseudo>    &#606060- Définir un niveau précis"));
        sender.sendMessage(ColorUtil.colorize("&#FFB300/niveau reset &#FFFFFF<pseudo>           &#606060- Remettre à zéro"));
    }

    // -------------------------------------------------------------------------
    // TabCompleter
    // -------------------------------------------------------------------------

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (!sender.hasPermission("niveaux.admin")) return List.of();

        if (args.length == 1) {
            String prefix = args[0].toLowerCase();
            return ACTIONS.stream()
                    .filter(a -> a.startsWith(prefix))
                    .toList();
        }

        String action = args[0].toLowerCase();

        // /niveau reset <pseudo>
        if (args.length == 2 && action.equals("reset")) {
            return onlinePlayers(args[1]);
        }

        // /niveau add|remove|set <valeur> <pseudo>
        if (args.length == 3 && (action.equals("add") || action.equals("remove") || action.equals("set"))) {
            return onlinePlayers(args[2]);
        }

        return List.of();
    }

    private List<String> onlinePlayers(String prefix) {
        String lower = prefix.toLowerCase();
        return Bukkit.getOnlinePlayers().stream()
                .map(Player::getName)
                .filter(n -> n.toLowerCase().startsWith(lower))
                .toList();
    }
}
