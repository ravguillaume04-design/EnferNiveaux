package fr.ravguillaume.niveaux;

import fr.ravguillaume.niveaux.commands.NiveauCommand;
import fr.ravguillaume.niveaux.config.ConfigManager;
import fr.ravguillaume.niveaux.data.PlayerData;
import fr.ravguillaume.niveaux.database.DatabaseManager;
import fr.ravguillaume.niveaux.listeners.PlayerConnectionListener;
import fr.ravguillaume.niveaux.listeners.PlayerDeathListener;
import fr.ravguillaume.niveaux.scheduler.PlaytimeScheduler;
import org.bukkit.Bukkit;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Point d'entrée principal du plugin Niveaux.
 *
 * Cycle de vie :
 *  onEnable  → config → BDD → listeners → command → scheduler
 *  onDisable → annule le scheduler → sauvegarde synchrone → ferme BDD
 */
public class NiveauxPlugin extends JavaPlugin {

    private ConfigManager    configManager;
    private DatabaseManager  databaseManager;
    private PlaytimeScheduler playtimeScheduler;

    /**
     * Cache en mémoire de tous les joueurs en ligne.
     * ConcurrentHashMap : accès depuis le thread Bukkit ET les threads asynchrones.
     */
    private final Map<UUID, PlayerData> playerCache = new ConcurrentHashMap<>();

    // -------------------------------------------------------------------------
    // Cycle de vie
    // -------------------------------------------------------------------------

    @Override
    public void onEnable() {
        saveDefaultConfig();

        configManager   = new ConfigManager(this);
        databaseManager = new DatabaseManager(this);

        if (!databaseManager.init()) {
            getLogger().severe("Arrêt du plugin : connexion MySQL impossible.");
            Bukkit.getPluginManager().disablePlugin(this);
            return;
        }

        // Listeners
        Bukkit.getPluginManager().registerEvents(new PlayerConnectionListener(this), this);
        Bukkit.getPluginManager().registerEvents(new PlayerDeathListener(this), this);

        // Commande
        NiveauCommand niveauCmd = new NiveauCommand(this);
        getCommand("niveau").setExecutor(niveauCmd);
        getCommand("niveau").setTabCompleter(niveauCmd);

        // Scheduler (cadence 1 minute, asynchrone)
        playtimeScheduler = new PlaytimeScheduler(this);
        playtimeScheduler.start();

        getLogger().info("Plugin Niveaux v" + getDescription().getVersion() + " activé.");
    }

    @Override
    public void onDisable() {
        if (playtimeScheduler != null) {
            playtimeScheduler.cancel();
        }

        // Sauvegarde synchrone finale (le scheduler est arrêté, pas de conflit)
        if (databaseManager != null && !playerCache.isEmpty()) {
            databaseManager.saveAllPlayers(playerCache.values());
            getLogger().info("Sauvegarde finale de " + playerCache.size() + " joueur(s) effectuée.");
        }

        if (databaseManager != null) {
            databaseManager.close();
        }

        getLogger().info("Plugin Niveaux désactivé.");
    }

    // -------------------------------------------------------------------------
    // Accesseurs
    // -------------------------------------------------------------------------

    public ConfigManager getConfigManager() {
        return configManager;
    }

    public DatabaseManager getDatabaseManager() {
        return databaseManager;
    }

    public Map<UUID, PlayerData> getPlayerCache() {
        return playerCache;
    }
}
