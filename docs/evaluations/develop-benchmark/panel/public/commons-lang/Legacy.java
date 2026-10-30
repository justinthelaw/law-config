import java.util.concurrent.TimeUnit;
import org.apache.commons.lang3.concurrent.TimedSemaphore;

public class Legacy {
    public static void main(String[] args) throws Exception {
        TimedSemaphore sem = new TimedSemaphore(20, TimeUnit.SECONDS, 2);
        try {
            sem.acquire();
            if (!sem.tryAcquire() || sem.tryAcquire() || sem.getAcquireCount() != 2)
                throw new AssertionError("permit accounting");
            sem.setLimit(0);
            if (!sem.tryAcquire()) throw new AssertionError("unlimited mode");
        } finally {
            sem.shutdown();
        }
        if (!sem.isShutdown()) throw new AssertionError("shutdown");
    }
}
