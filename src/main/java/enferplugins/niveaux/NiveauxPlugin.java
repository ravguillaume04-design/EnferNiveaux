package enferplugins.niveaux;

import enferplugins.niveaux.commands.NiveauCommand;
import enferplugins.niveaux.config.ConfigManager;
import enferplugins.niveaux.data.PlayerData;
import enferplugins.niveaux.database.DatabaseManager;
import enferplugins.niveaux.listeners.PlayerConnectionListener;
import enferplugins.niveaux.listeners.PlayerDeathListener;
import enferplugins.niveaux.scheduler.PlaytimeScheduler;
import org.bukkit.Bukkit;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public class NiveauxPlugin extends JavaPlugin {

    private ConfigManager configManager;
    private DatabaseManager databaseManager;
    private PlaytimeScheduler playtimeScheduler;
    private final Map<UUID, PlayerData> playerCache = new ConcurrentHashMap<>();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        configManager = new ConfigManager(this);
        databaseManager = new DatabaseManager(this);
        if (!databaseManager.init()) {
            getLogger().severe("Arrêt du plugin : connexion MySQL impossible.");
            Bukkit.getPluginManager().disablePlugin(this);
            return;
        }
        Bukkit.getPluginManager().registerEvents(new PlayerConnectionListener(this), this);
        Bukkit.getPluginManager().registerEvents(new PlayerDeathListener(this), this);
        NiveauCommand niveauCmd = new NiveauCommand(this);
        getCommand("niveau").setExecutor(niveauCmd);
        getCommand("niveau").setTabCompleter(niveauCmd);
        playtimeScheduler = new PlaytimeScheduler(this);
        playtimeScheduler.start();
        getLogger().info("EnferNiveaux v" + getDescription().getVersion() + " activé.");
    }

    @Override
    public void onDisable() {
        if (playtimeScheduler != null) playtimeScheduler.cancel();
        if (databaseManager != null && !playerCache.isEmpty()) {
            databaseManager.saveAllPlayers(playerCache.values());
            getLogger().info("Sauvegarde finale de " + playerCache.size() + " joueur(s) effectuée.");
        }
        if (databaseManager != null) databaseManager.close();
        getLogger().info("EnferNiveaux désactivé.");
    }

    public ConfigManager getConfigManager() { return configManager; }
    public DatabaseManager getDatabaseManager() { return databaseManager; }
    public Map<UUID, PlayerData> getPlayerCache() { return playerCache; }
}
