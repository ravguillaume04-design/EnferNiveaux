package fr.ravguillaume.niveaux.config;

import fr.ravguillaume.niveaux.NiveauxPlugin;

import java.util.List;

/**
 * Façade simple sur le config.yml Bukkit.
 * Toutes les valeurs sont lues à chaud (pas de cache interne),
 * ce qui permet un /reload sans redémarrer le plugin.
 */
public class ConfigManager {

    private final NiveauxPlugin plugin;

    public ConfigManager(NiveauxPlugin plugin) {
        this.plugin = plugin;
    }

    public void reload() {
        plugin.reloadConfig();
    }

    // -------------------------------------------------------------------------
    // Database
    // -------------------------------------------------------------------------

    public String getDatabaseHost() {
        return plugin.getConfig().getString("database.host", "localhost");
    }

    public int getDatabasePort() {
        return plugin.getConfig().getInt("database.port", 3306);
    }

    public String getDatabaseName() {
        return plugin.getConfig().getString("database.name", "minecraft");
    }

    public String getDatabaseUser() {
        return plugin.getConfig().getString("database.username", "root");
    }

    public String getDatabasePassword() {
        return plugin.getConfig().getString("database.password", "password");
    }

    // -------------------------------------------------------------------------
    // Gameplay
    // -------------------------------------------------------------------------

    /**
     * Retourne la liste des noms de mondes autorisés pour la progression.
     */
    public List<String> getAuthorizedWorlds() {
        return plugin.getConfig().getStringList("mondes-autorises");
    }

    /**
     * Retourne l'intervalle d'auto-save en minutes (minimum 1).
     */
    public int getAutoSaveInterval() {
        return Math.max(1, plugin.getConfig().getInt("auto-save-interval", 5));
    }
}
