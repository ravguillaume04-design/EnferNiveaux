package fr.ravguillaume.niveaux.commands;

import fr.ravguillaume.niveaux.NiveauxPlugin;
import fr.ravguillaume.niveaux.data.PlayerData;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.util.Arrays;
import java.util.List;
import java.util.function.Consumer;

/**
 * Commandes administrateur pour gérer les niveaux des joueurs.
 *
 * Usage :
 *   /niveau get    <pseudo>
 *   /niveau reset  <pseudo>
 *   /niveau add    <valeur> <pseudo>
 *   /niveau remove <valeur> <pseudo>
 *   /niveau set    <valeur> <pseudo>
 */
public class NiveauCommand implements CommandExecutor, TabCompleter {

    private static final List<String> ACTIONS = Arrays.asList(
            "add", "remove", "set", "reset", "get"
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
            sender.sendMessage("§cVous n'avez pas la permission d'utiliser cette commande.");
            return true;
        }

        if (args.length < 1) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "get"    -> handleGet(sender, args);
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

    private void handleGet(CommandSender sender, String[] args) {
        if (args.length < 2) { sender.sendMessage("§cUsage : /niveau get <pseudo>"); return; }

        resolveData(sender, args[1], data ->
            sender.sendMessage(
                "§7Joueur §6" + data.getName() +
                " §7: §6Niveau " + data.getLevel() +
                " §7(§e" + data.getMinutes() + " §7min)"
            )
        );
    }

    private void handleReset(CommandSender sender, String[] args) {
        if (args.length < 2) { sender.sendMessage("§cUsage : /niveau reset <pseudo>"); return; }

        modifyData(sender, args[1], data -> {
            int old = data.getLevel();
            data.reset();
            sender.sendMessage(
                "§aLe niveau de §6" + data.getName() + " §aa été réinitialisé. " +
                "§7(ancien niveau : §6" + old + "§7)"
            );
            notifyTarget(data.getName(), "§cVotre niveau a été réinitialisé par un administrateur.");
        });
    }

    private void handleAdd(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage("§cUsage : /niveau add <valeur> <pseudo>"); return; }

        int amount = parseNonNegativeInt(sender, args[1]);
        if (amount < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.addLevel(amount);
            sender.sendMessage(
                "§a+" + amount + " niveau(x) ajouté(s) à §6" + data.getName() +
                "§a. §7(§6" + old + " §7→ §6" + data.getLevel() + "§7)"
            );
            notifyTarget(data.getName(),
                "§aUn administrateur vous a ajouté §6" + amount +
                " §aniveau(x). Vous êtes maintenant §6niveau " + data.getLevel() + "§a."
            );
        });
    }

    private void handleRemove(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage("§cUsage : /niveau remove <valeur> <pseudo>"); return; }

        int amount = parseNonNegativeInt(sender, args[1]);
        if (amount < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.removeLevel(amount);
            sender.sendMessage(
                "§c-" + amount + " niveau(x) retiré(s) à §6" + data.getName() +
                "§c. §7(§6" + old + " §7→ §6" + data.getLevel() + "§7)"
            );
            notifyTarget(data.getName(),
                "§cUn administrateur vous a retiré §6" + amount +
                " §cniveau(x). Vous êtes maintenant §6niveau " + data.getLevel() + "§c."
            );
        });
    }

    private void handleSet(CommandSender sender, String[] args) {
        if (args.length < 3) { sender.sendMessage("§cUsage : /niveau set <valeur> <pseudo>"); return; }

        int level = parseNonNegativeInt(sender, args[1]);
        if (level < 0) return;

        modifyData(sender, args[2], data -> {
            int old = data.getLevel();
            data.setLevel(level);
            sender.sendMessage(
                "§aNiveau de §6" + data.getName() + " §adéfini à §6" + data.getLevel() +
                "§a. §7(§6" + old + " §7→ §6" + data.getLevel() +
                "§7, temps recalculé : §e" + data.getMinutes() + " §7min)"
            );
            notifyTarget(data.getName(),
                "§aUn administrateur a défini votre niveau à §6" + data.getLevel() + "§a."
            );
        });
    }

    // -------------------------------------------------------------------------
    // Résolution des données (cache → DB)
    // -------------------------------------------------------------------------

    /**
     * Résout les données d'un joueur (lecture seule) et exécute le callback
     * sur le thread principal. Cherche d'abord dans le cache, puis en base.
     */
    private void resolveData(CommandSender sender, String targetName, Consumer<PlayerData> callback) {
        Player online = Bukkit.getPlayerExact(targetName);
        if (online != null) {
            PlayerData cached = plugin.getPlayerCache().get(online.getUniqueId());
            if (cached != null) {
                callback.accept(cached);
                return;
            }
        }

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            PlayerData data = plugin.getDatabaseManager().loadPlayerByName(targetName);
            Bukkit.getScheduler().runTask(plugin, () -> {
                if (data == null) {
                    sender.sendMessage("§cJoueur §6" + targetName + " §cintrouvable en base de données.");
                    return;
                }
                callback.accept(data);
            });
        });
    }

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
                    sender.sendMessage("§cJoueur §6" + targetName + " §cintrouvable en base de données.");
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
     * Envoie un message au joueur cible s'il est en ligne.
     */
    private void notifyTarget(String name, String message) {
        Player target = Bukkit.getPlayerExact(name);
        if (target != null) target.sendMessage(message);
    }

    /**
     * Parse un entier >= 0. Retourne -1 (et envoie un message d'erreur) si invalide.
     */
    private int parseNonNegativeInt(CommandSender sender, String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value < 0) {
                sender.sendMessage("§cLa valeur doit être un entier positif ou zéro.");
                return -1;
            }
            return value;
        } catch (NumberFormatException e) {
            sender.sendMessage("§c\"" + raw + "\" n'est pas un nombre valide.");
            return -1;
        }
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage("§6§l=== Commandes /niveau ===");
        sender.sendMessage("§e/niveau get <pseudo>            §7- Voir le niveau d'un joueur");
        sender.sendMessage("§e/niveau add <valeur> <pseudo>   §7- Ajouter des niveaux");
        sender.sendMessage("§e/niveau remove <valeur> <pseudo>§7- Retirer des niveaux");
        sender.sendMessage("§e/niveau set <valeur> <pseudo>   §7- Définir un niveau précis");
        sender.sendMessage("§e/niveau reset <pseudo>          §7- Remettre à zéro");
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

        // /niveau get <pseudo>  ou  /niveau reset <pseudo>
        if (args.length == 2 && (action.equals("get") || action.equals("reset"))) {
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
