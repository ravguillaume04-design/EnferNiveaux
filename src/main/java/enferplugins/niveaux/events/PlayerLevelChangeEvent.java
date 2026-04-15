package enferplugins.niveaux.events;

import org.bukkit.event.Event;
import org.bukkit.event.HandlerList;

import java.util.UUID;

public class PlayerLevelChangeEvent extends Event {

    private static final HandlerList HANDLERS = new HandlerList();

    public enum Reason { PLAYTIME, DEATH_RESET, ADMIN_ADD, ADMIN_REMOVE, ADMIN_SET, ADMIN_RESET }

    private final UUID playerUuid;
    private final String playerName;
    private final int oldLevel;
    private final int newLevel;
    private final Reason reason;

    public PlayerLevelChangeEvent(UUID playerUuid, String playerName, int oldLevel, int newLevel, Reason reason) {
        this.playerUuid = playerUuid; this.playerName = playerName;
        this.oldLevel = oldLevel; this.newLevel = newLevel; this.reason = reason;
    }

    public UUID getPlayerUuid() { return playerUuid; }
    public String getPlayerName() { return playerName; }
    public int getOldLevel() { return oldLevel; }
    public int getNewLevel() { return newLevel; }
    public Reason getReason() { return reason; }

    @Override public HandlerList getHandlers() { return HANDLERS; }
    public static HandlerList getHandlerList() { return HANDLERS; }
}
