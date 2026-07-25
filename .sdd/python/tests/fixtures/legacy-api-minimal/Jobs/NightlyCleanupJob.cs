using System;

namespace LegacyApi.Jobs
{
    // Orphan backend module — not reachable from any controller or page.
    public class NightlyCleanupJob
    {
        public void Run()
        {
            PurgeStaleSessions();
            ArchiveOldOrders();
        }

        private void PurgeStaleSessions()
        {
            Console.WriteLine("purging");
        }

        private void ArchiveOldOrders()
        {
            Console.WriteLine("archiving");
        }
    }
}
